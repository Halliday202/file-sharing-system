import javax.crypto.Cipher;
import javax.crypto.spec.IvParameterSpec;
import javax.crypto.spec.SecretKeySpec;

public class CryptoUtil {

    private static final String AES_KEY_HEX =
        "00112233445566778899AABBCCDDEEFF00112233445566778899AABBCCDDEEFF";

    private static final int IV_LENGTH = 16;

    private static byte[] hexToBytes(String hex) {
        int len = hex.length();
        byte[] out = new byte[len / 2];
        for (int i = 0; i < len; i += 2) {
            out[i / 2] = (byte) ((Character.digit(hex.charAt(i), 16) << 4)
                                + Character.digit(hex.charAt(i + 1), 16));
        }
        return out;
    }

    public static byte[] decrypt(byte[] payload) throws Exception {
        if (payload.length < IV_LENGTH) {
            throw new IllegalArgumentException("payload too short to contain IV");
        }

        byte[] iv = new byte[IV_LENGTH];
        System.arraycopy(payload, 0, iv, 0, IV_LENGTH);

        byte[] ciphertext = new byte[payload.length - IV_LENGTH];
        System.arraycopy(payload, IV_LENGTH, ciphertext, 0, ciphertext.length);

        byte[] keyBytes = hexToBytes(AES_KEY_HEX);
        SecretKeySpec keySpec = new SecretKeySpec(keyBytes, "AES");
        IvParameterSpec ivSpec = new IvParameterSpec(iv);

        Cipher cipher = Cipher.getInstance("AES/CBC/PKCS5Padding");
        cipher.init(Cipher.DECRYPT_MODE, keySpec, ivSpec);
        return cipher.doFinal(ciphertext);
    }
}
