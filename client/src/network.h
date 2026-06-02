#ifndef NETWORK_H
#define NETWORK_H

#include <vector>
#include <string>
#include <cstdint>

// sends a full packet to the manager and returns the response string
std::string send_packet(const std::string& host, int port,
                        const std::vector<uint8_t>& packet);

#endif
