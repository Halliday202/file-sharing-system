import java.net.ServerSocket;
import java.net.Socket;

public class StorageDaemon {

    public static void main(String[] args) {
        if (args.length < 1) {
            System.err.println("usage: java StorageDaemon <port>");
            System.exit(1);
        }

        int port;
        try {
            port = Integer.parseInt(args[0]);
        } catch (NumberFormatException e) {
            System.err.println("invalid port: " + args[0]);
            System.exit(1);
            return;
        }

        String storageRoot = "stored_files";

        System.out.println("[StorageDaemon] starting on port " + port);
        System.out.println("[StorageDaemon] storage root: " + storageRoot + "/" + port);

        try (ServerSocket serverSocket = new ServerSocket(port)) {
            System.out.println("[StorageDaemon] listening on port " + port + "...");

            while (true) {
                Socket client = serverSocket.accept();
                System.out.println("[StorageDaemon:" + port + "] accepted connection from "
                    + client.getInetAddress().getHostAddress());

                Thread handler = new Thread(new ConnectionHandler(client, port, storageRoot));
                handler.start();
            }
        } catch (Exception e) {
            System.err.println("[StorageDaemon] fatal: " + e.getMessage());
            e.printStackTrace();
            System.exit(1);
        }
    }
}
