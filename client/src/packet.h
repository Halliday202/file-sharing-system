#ifndef PACKET_H
#define PACKET_H

#include <vector>
#include <string>
#include <cstdint>

// builds a NetworkPacket: JSON header + "\n\n" + encrypted payload
std::vector<uint8_t> build_packet(const std::string& file_id,
                                   const std::string& filename,
                                   const std::vector<uint8_t>& encrypted_payload);

// generates a simple unique id (timestamp + random suffix)
std::string generate_id();

// extracts basename from a full file path
std::string extract_basename(const std::string& filepath);

#endif
