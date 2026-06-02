#ifndef CRYPTO_H
#define CRYPTO_H

#include <vector>
#include <cstdint>
#include <string>

// AES-256-CBC encryption using OpenSSL EVP API.
// returns IV (16 bytes) prepended to ciphertext.
std::vector<uint8_t> aes_encrypt(const std::vector<uint8_t>& plaintext);

// shared 256-bit key (hex string) -- must match Python config.py and Java CryptoUtil
extern const std::string AES_KEY_HEX;

#endif
