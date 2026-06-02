#include <iostream>
#include <fstream>
#include <vector>
#include <string>
#include <algorithm>

#include "crypto.h"
#include "packet.h"
#include "network.h"

static const std::string MANAGER_HOST = "127.0.0.1";
static const int MANAGER_PORT = 9000;

static std::vector<uint8_t> read_file(const std::string& path) {
    std::ifstream file(path, std::ios::binary | std::ios::ate);
    if (!file.is_open()) {
        throw std::runtime_error("cannot open file: " + path);
    }
    std::streamsize size = file.tellg();
    file.seekg(0, std::ios::beg);

    std::vector<uint8_t> buffer(static_cast<size_t>(size));
    if (!file.read(reinterpret_cast<char*>(buffer.data()), size)) {
        throw std::runtime_error("failed to read file: " + path);
    }
    return buffer;
}

int main() {
    std::cout << "=== Distributed File Sharing Client ===" << std::endl;
    std::cout << "Manager: " << MANAGER_HOST << ":" << MANAGER_PORT << std::endl;
    std::cout << std::endl;

    std::string filepath;
    std::cout << "Enter file path to upload: ";
    std::getline(std::cin, filepath);

    if (filepath.empty()) {
        std::cerr << "error: no file path provided" << std::endl;
        return 1;
    }

    // trim leading/trailing whitespace
    filepath.erase(filepath.begin(),
        std::find_if(filepath.begin(), filepath.end(),
            [](unsigned char c){ return !std::isspace(c); }));
    filepath.erase(
        std::find_if(filepath.rbegin(), filepath.rend(),
            [](unsigned char c){ return !std::isspace(c); }).base(),
        filepath.end());

    // strip surrounding quotes if the user dragged a file into the terminal
    if (filepath.size() >= 2 && filepath.front() == '"' && filepath.back() == '"') {
        filepath = filepath.substr(1, filepath.size() - 2);
    }

    try {
        std::cout << "reading file..." << std::endl;
        std::vector<uint8_t> file_data = read_file(filepath);
        std::cout << "file size: " << file_data.size() << " bytes" << std::endl;

        std::cout << "encrypting (AES-256-CBC)..." << std::endl;
        std::vector<uint8_t> encrypted = aes_encrypt(file_data);
        std::cout << "encrypted payload: " << encrypted.size() << " bytes (includes 16-byte IV)" << std::endl;

        std::string file_id = generate_id();
        std::string filename = extract_basename(filepath);

        std::cout << "building packet (id=" << file_id << ", file=\"" << filename << "\")..." << std::endl;
        std::vector<uint8_t> packet = build_packet(file_id, filename, encrypted);

        std::cout << "sending to manager at " << MANAGER_HOST << ":" << MANAGER_PORT << "..." << std::endl;
        std::string response = send_packet(MANAGER_HOST, MANAGER_PORT, packet);

        std::cout << "server response: " << response << std::endl;

    } catch (const std::exception& e) {
        std::cerr << "error: " << e.what() << std::endl;
        return 1;
    }

    return 0;
}
