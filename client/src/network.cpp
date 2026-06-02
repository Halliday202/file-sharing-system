#include "network.h"
#include <stdexcept>
#include <cstring>

#ifdef _WIN32
    #include <winsock2.h>
    #include <ws2tcpip.h>
    #pragma comment(lib, "ws2_32.lib")
#else
    #include <sys/socket.h>
    #include <arpa/inet.h>
    #include <unistd.h>
    #define SOCKET int
    #define INVALID_SOCKET (-1)
    #define SOCKET_ERROR (-1)
    #define closesocket close
#endif

class WinsockGuard {
public:
    WinsockGuard() {
#ifdef _WIN32
        WSADATA wsa;
        if (WSAStartup(MAKEWORD(2, 2), &wsa) != 0) {
            throw std::runtime_error("WSAStartup failed");
        }
#endif
    }
    ~WinsockGuard() {
#ifdef _WIN32
        WSACleanup();
#endif
    }
};

std::string send_packet(const std::string& host, int port,
                        const std::vector<uint8_t>& packet) {
    WinsockGuard wsa_guard;

    SOCKET sock = socket(AF_INET, SOCK_STREAM, IPPROTO_TCP);
    if (sock == INVALID_SOCKET) {
        throw std::runtime_error("socket() failed");
    }

    struct sockaddr_in addr;
    std::memset(&addr, 0, sizeof(addr));
    addr.sin_family = AF_INET;
    addr.sin_port = htons(static_cast<unsigned short>(port));
    addr.sin_addr.s_addr = inet_addr(host.c_str());

    if (connect(sock, (struct sockaddr*)&addr, sizeof(addr)) == SOCKET_ERROR) {
        closesocket(sock);
        throw std::runtime_error("connect() failed to " + host + ":" + std::to_string(port));
    }

    // send the full packet
    size_t total_sent = 0;
    while (total_sent < packet.size()) {
        int sent = send(sock, reinterpret_cast<const char*>(packet.data() + total_sent),
                        static_cast<int>(packet.size() - total_sent), 0);
        if (sent == SOCKET_ERROR) {
            closesocket(sock);
            throw std::runtime_error("send() failed");
        }
        total_sent += sent;
    }

    // read response (single line, json)
    std::string response;
    char buf[1024];
    while (true) {
        int received = recv(sock, buf, sizeof(buf) - 1, 0);
        if (received <= 0) break;
        buf[received] = '\0';
        response += buf;
        if (response.find('\n') != std::string::npos) break;
    }

    closesocket(sock);
    return response;
}
