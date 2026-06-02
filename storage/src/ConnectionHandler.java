import java.io.InputStream;
import java.io.OutputStream;
import java.net.Socket;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.Map;

public class ConnectionHandler implements Runnable {

    private final Socket clientSocket;
    private final int port;
    private final String storageRoot;

    public ConnectionHandler(Socket clientSocket, int port, String storageRoot) {
        this.clientSocket = clientSocket;
        this.port = port;
        this.storageRoot = storageRoot;
    }

    @Override
    public void run() {
        try (
            InputStream in = clientSocket.getInputStream();
            OutputStream out = clientSocket.getOutputStream()
        ) {
            PacketParser packet = PacketParser.readFrom(in);
            Map<String, String> header = packet.getHeader();

            String requestType = header.getOrDefault("type", "upload");

            if ("download".equals(requestType)) {
                handleDownload(header, out);
            } else {
                handleUpload(header, packet.getPayload(), out);
            }

        } catch (Exception e) {
            System.err.println("[node:" + port + "] error handling connection: " + e.getMessage());
            try {
                OutputStream out = clientSocket.getOutputStream();
                String errorMsg = "{\"status\":\"error\",\"node\":" + port
                    + ",\"reason\":\"" + e.getMessage().replace("\"", "'") + "\"}\n";
                out.write(errorMsg.getBytes("UTF-8"));
                out.flush();
            } catch (Exception ignored) {}
        } finally {
            try { clientSocket.close(); } catch (Exception ignored) {}
        }
    }

    private void handleUpload(Map<String, String> header, byte[] payloadBytes, OutputStream out) throws Exception {
        String rawFilename = header.getOrDefault("filename", "unnamed");
        String fileId = header.getOrDefault("id", "unknown");
        String safeFilename = PathSanitizer.sanitize(rawFilename);

        System.out.println("[node:" + port + "] upload id=" + fileId
            + " original=\"" + rawFilename + "\" safe=\"" + safeFilename + "\""
            + " payload=" + payloadBytes.length + " bytes");

        byte[] decrypted = CryptoUtil.decrypt(payloadBytes);

        Path nodeDir = Paths.get(storageRoot, String.valueOf(port));
        Files.createDirectories(nodeDir);

        Path destPath = nodeDir.resolve(safeFilename);

        if (!destPath.toAbsolutePath().normalize()
                .startsWith(nodeDir.toAbsolutePath().normalize())) {
            String errorMsg = "{\"status\":\"error\",\"node\":" + port
                + ",\"reason\":\"path traversal blocked\"}\n";
            out.write(errorMsg.getBytes("UTF-8"));
            out.flush();
            System.err.println("[node:" + port + "] path traversal attempt blocked: " + rawFilename);
            return;
        }

        Files.write(destPath, decrypted);
        System.out.println("[node:" + port + "] saved " + destPath + " (" + decrypted.length + " bytes)");

        String ack = "{\"status\":\"saved\",\"node\":" + port + "}\n";
        out.write(ack.getBytes("UTF-8"));
        out.flush();
    }

    private void handleDownload(Map<String, String> header, OutputStream out) throws Exception {
        String rawFilename = header.getOrDefault("filename", "unnamed");
        String safeFilename = PathSanitizer.sanitize(rawFilename);

        System.out.println("[node:" + port + "] download request for \"" + safeFilename + "\"");

        Path nodeDir = Paths.get(storageRoot, String.valueOf(port));
        Path filePath = nodeDir.resolve(safeFilename);

        if (!filePath.toAbsolutePath().normalize()
                .startsWith(nodeDir.toAbsolutePath().normalize())) {
            String errorMsg = "{\"status\":\"error\",\"node\":" + port
                + ",\"reason\":\"path traversal blocked\"}\n";
            out.write(errorMsg.getBytes("UTF-8"));
            out.flush();
            return;
        }

        if (!Files.exists(filePath)) {
            String errorMsg = "{\"status\":\"error\",\"node\":" + port
                + ",\"reason\":\"file not found\"}\n";
            out.write(errorMsg.getBytes("UTF-8"));
            out.flush();
            System.err.println("[node:" + port + "] file not found: " + filePath);
            return;
        }

        byte[] plaintext = Files.readAllBytes(filePath);
        byte[] encrypted = CryptoUtil.encrypt(plaintext);

        // build response packet: header + \n\n + encrypted payload
        String respHeader = "{\"type\":\"download_response\",\"filename\":\""
            + safeFilename + "\",\"payloadSize\":" + encrypted.length
            + ",\"node\":" + port + "}";

        out.write(respHeader.getBytes("UTF-8"));
        out.write("\n\n".getBytes("UTF-8"));
        out.write(encrypted);
        out.flush();

        System.out.println("[node:" + port + "] sent " + safeFilename
            + " (" + plaintext.length + " bytes plaintext, "
            + encrypted.length + " bytes encrypted)");
    }
}
