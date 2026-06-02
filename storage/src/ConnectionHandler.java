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

            String rawFilename = header.getOrDefault("filename", "unnamed");
            String fileId = header.getOrDefault("id", "unknown");
            String safeFilename = PathSanitizer.sanitize(rawFilename);

            System.out.println("[node:" + port + "] received file id=" + fileId
                + " original=\"" + rawFilename + "\" safe=\"" + safeFilename + "\""
                + " payload=" + packet.getPayload().length + " bytes");

            byte[] decrypted = CryptoUtil.decrypt(packet.getPayload());

            // write to stored_files/<port>/<safe_filename>
            Path nodeDir = Paths.get(storageRoot, String.valueOf(port));
            Files.createDirectories(nodeDir);

            Path destPath = nodeDir.resolve(safeFilename);

            // final safety check: ensure resolved path stays inside nodeDir
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
}
