#include "packet.h"
#include <ctime>
#include <cstdlib>
#include <sstream>
#include <algorithm>

std::string generate_id() {
    // simple unique id: unix timestamp + 4-digit random suffix
    std::srand(static_cast<unsigned>(std::time(nullptr)));
    std::ostringstream oss;
    oss << std::time(nullptr) << "-" << (std::rand() % 10000);
    return oss.str();
}

std::string extract_basename(const std::string& filepath) {
    // handle both / and backslash separators
    size_t pos = filepath.find_last_of("/\\");
    if (pos == std::string::npos) {
        return filepath;
    }
    return filepath.substr(pos + 1);
}

std::vector<uint8_t> build_packet(const std::string& file_id,
                                   const std::string& filename,
                                   const std::vector<uint8_t>& encrypted_payload) {
    // build JSON header manually (no external json library needed)
    std::ostringstream json;
    json << "{"
         << "\"id\":\"" << file_id << "\","
         << "\"type\":\"upload\","
         << "\"filename\":\"" << filename << "\","
         << "\"payloadSize\":" << encrypted_payload.size()
         << "}";

    std::string header = json.str();

    // assemble: header + \n\n + payload
    std::vector<uint8_t> packet;
    packet.reserve(header.size() + 2 + encrypted_payload.size());

    packet.insert(packet.end(), header.begin(), header.end());
    packet.push_back('\n');
    packet.push_back('\n');
    packet.insert(packet.end(), encrypted_payload.begin(), encrypted_payload.end());

    return packet;
}
