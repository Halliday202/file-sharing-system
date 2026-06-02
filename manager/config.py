MANAGER_HOST = "127.0.0.1"
MANAGER_PORT = 9000

STORAGE_NODES = [
    ("127.0.0.1", 8001),
    ("127.0.0.1", 8002),
    ("127.0.0.1", 8003),
]

# shared 256-bit AES key (hex) -- must match Java CryptoUtil and C++ client
AES_KEY_HEX = "00112233445566778899AABBCCDDEEFF00112233445566778899AABBCCDDEEFF"

# "strong" = wait for all nodes before acking client
# "eventual" = ack client immediately, replicate in background
CONSISTENCY_MODE = "strong"

# dashboard reads state from this file (written by the server)
STATE_FILE = "state.json"
