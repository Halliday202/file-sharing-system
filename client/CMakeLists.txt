cmake_minimum_required(VERSION 3.10)
project(FileShareClient LANGUAGES CXX)
set(CMAKE_CXX_STANDARD 14)

find_package(OpenSSL REQUIRED)

add_executable(client
    src/main.cpp
    src/crypto.cpp
    src/packet.cpp
    src/network.cpp
)

target_include_directories(client PRIVATE ${OPENSSL_INCLUDE_DIR})
target_link_libraries(client PRIVATE OpenSSL::Crypto)

if(WIN32)
    target_link_libraries(client PRIVATE ws2_32)
endif()
