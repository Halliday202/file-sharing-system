import java.io.InputStream;
import java.io.ByteArrayOutputStream;
import java.util.HashMap;
import java.util.Map;

public class PacketParser {

    private final Map<String, String> header;
    private final byte[] payload;

    public PacketParser(Map<String, String> header, byte[] payload) {
        this.header = header;
        this.payload = payload;
    }

    public Map<String, String> getHeader() {
        return header;
    }

    public byte[] getPayload() {
        return payload;
    }

    public String getHeaderValue(String key) {
        return header.getOrDefault(key, "");
    }

    /**
     * reads a NetworkPacket from a raw TCP input stream.
     * protocol: JSON header (utf-8) + "\n\n" + binary payload
     */
    public static PacketParser readFrom(InputStream in) throws Exception {
        ByteArrayOutputStream headerBuf = new ByteArrayOutputStream();
        int prev = -1;
        int curr;

        // read byte-by-byte until we hit \n\n
        while ((curr = in.read()) != -1) {
            headerBuf.write(curr);
            if (prev == '\n' && curr == '\n') {
                break;
            }
            prev = curr;
        }

        if (curr == -1 && headerBuf.size() == 0) {
            throw new Exception("connection closed before header received");
        }

        // strip the trailing \n\n from header bytes
        byte[] rawHeader = headerBuf.toByteArray();
        String headerStr = new String(rawHeader, 0, rawHeader.length - 2, "UTF-8").trim();

        Map<String, String> headerMap = parseJson(headerStr);

        String sizeStr = headerMap.get("payloadSize");
        if (sizeStr == null) {
            throw new Exception("missing payloadSize in header");
        }
        int payloadSize = Integer.parseInt(sizeStr);

        // read exactly payloadSize bytes
        byte[] payload = new byte[payloadSize];
        int totalRead = 0;
        while (totalRead < payloadSize) {
            int bytesRead = in.read(payload, totalRead, payloadSize - totalRead);
            if (bytesRead == -1) {
                throw new Exception(
                    "connection closed after " + totalRead + "/" + payloadSize + " payload bytes");
            }
            totalRead += bytesRead;
        }

        return new PacketParser(headerMap, payload);
    }

    /**
     * lightweight JSON parser for flat objects like:
     * {"id":"abc","type":"upload","filename":"test.pdf","payloadSize":4096}
     * no external dependencies needed.
     */
    private static Map<String, String> parseJson(String json) {
        Map<String, String> map = new HashMap<>();

        // strip outer braces
        json = json.trim();
        if (json.startsWith("{")) json = json.substring(1);
        if (json.endsWith("}")) json = json.substring(0, json.length() - 1);

        // split by comma, but respect quoted strings
        StringBuilder current = new StringBuilder();
        boolean inQuotes = false;
        java.util.List<String> pairs = new java.util.ArrayList<>();

        for (int i = 0; i < json.length(); i++) {
            char c = json.charAt(i);
            if (c == '"') {
                inQuotes = !inQuotes;
                current.append(c);
            } else if (c == ',' && !inQuotes) {
                pairs.add(current.toString());
                current.setLength(0);
            } else {
                current.append(c);
            }
        }
        if (current.length() > 0) {
            pairs.add(current.toString());
        }

        for (String pair : pairs) {
            int colonIdx = pair.indexOf(':');
            if (colonIdx < 0) continue;
            String key = pair.substring(0, colonIdx).trim().replace("\"", "");
            String value = pair.substring(colonIdx + 1).trim().replace("\"", "");
            map.put(key, value);
        }

        return map;
    }
}
