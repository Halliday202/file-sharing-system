import java.io.File;
import java.nio.file.Path;
import java.nio.file.Paths;

public class PathSanitizer {

    public static String sanitize(String filename) {
        if (filename == null || filename.isEmpty()) {
            return "unnamed_file";
        }

        // strip null bytes
        filename = filename.replace("\0", "");

        // normalize separators to forward slash, then extract basename
        filename = filename.replace("\\", "/");

        // strip all directory traversal sequences before taking basename
        filename = filename.replace("../", "");
        filename = filename.replace("./", "");

        // extract only the last path component (basename)
        int lastSlash = filename.lastIndexOf('/');
        if (lastSlash >= 0) {
            filename = filename.substring(lastSlash + 1);
        }

        // strip leading dots (hidden files / residual traversal)
        while (filename.startsWith(".")) {
            filename = filename.substring(1);
        }

        // remove any remaining characters that aren't alphanumeric, dot, hyphen, or underscore
        filename = filename.replaceAll("[^a-zA-Z0-9._\\-]", "_");

        if (filename.isEmpty()) {
            filename = "unnamed_file";
        }

        // final safety: resolve against a dummy base and verify it doesn't escape
        Path base = Paths.get("base");
        Path resolved = base.resolve(filename).normalize();
        if (!resolved.startsWith(base)) {
            return "unnamed_file";
        }

        return filename;
    }
}
