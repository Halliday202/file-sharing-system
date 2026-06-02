#include "crypto.h"
#include <openssl/evp.h>
#include <openssl/rand.h>
#include <openssl/err.h>
#include <stdexcept>
#include <cstring>

const std::string AES_KEY_HEX =
    "00112233445566778899AABBCCDDEEFF00112233445566778899AABBCCDDEEFF";

static std::vector<uint8_t> hex_to_bytes(const std::string& hex) {
    std::vector<uint8_t> bytes;
    for (size_t i = 0; i < hex.length(); i += 2) {
        uint8_t byte = static_cast<uint8_t>(
            std::stoi(hex.substr(i, 2), nullptr, 16));
        bytes.push_back(byte);
    }
    return bytes;
}

std::vector<uint8_t> aes_encrypt(const std::vector<uint8_t>& plaintext) {
    const int IV_LEN = 16;
    std::vector<uint8_t> key_bytes = hex_to_bytes(AES_KEY_HEX);

    // generate random IV
    unsigned char iv[IV_LEN];
    if (RAND_bytes(iv, IV_LEN) != 1) {
        throw std::runtime_error("RAND_bytes failed");
    }

    EVP_CIPHER_CTX* ctx = EVP_CIPHER_CTX_new();
    if (!ctx) {
        throw std::runtime_error("EVP_CIPHER_CTX_new failed");
    }

    if (EVP_EncryptInit_ex(ctx, EVP_aes_256_cbc(), nullptr,
                           key_bytes.data(), iv) != 1) {
        EVP_CIPHER_CTX_free(ctx);
        throw std::runtime_error("EVP_EncryptInit_ex failed");
    }

    // output buffer: plaintext size + one full block for padding
    int block_size = EVP_CIPHER_block_size(EVP_aes_256_cbc());
    std::vector<uint8_t> ciphertext(plaintext.size() + block_size);
    int out_len = 0;
    int total_len = 0;

    if (EVP_EncryptUpdate(ctx, ciphertext.data(), &out_len,
                          plaintext.data(),
                          static_cast<int>(plaintext.size())) != 1) {
        EVP_CIPHER_CTX_free(ctx);
        throw std::runtime_error("EVP_EncryptUpdate failed");
    }
    total_len = out_len;

    if (EVP_EncryptFinal_ex(ctx, ciphertext.data() + total_len,
                            &out_len) != 1) {
        EVP_CIPHER_CTX_free(ctx);
        throw std::runtime_error("EVP_EncryptFinal_ex failed");
    }
    total_len += out_len;
    EVP_CIPHER_CTX_free(ctx);

    ciphertext.resize(total_len);

    // prepend IV to ciphertext: [IV || ciphertext]
    std::vector<uint8_t> result;
    result.reserve(IV_LEN + total_len);
    result.insert(result.end(), iv, iv + IV_LEN);
    result.insert(result.end(), ciphertext.begin(), ciphertext.end());

    return result;
}
