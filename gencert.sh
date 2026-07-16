#!/usr/bin/env bash
SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" &>/dev/null && pwd)
CERT_DIR="${SCRIPT_DIR}/cert"
SUBJECT='/C=US/ST=CA/L=SanFrancisco/O=ShareText-LAN'
INTERFACE=( 'wlo1' 'eno1' )

echo "[*] generating certificates and keys..."

# create cert folder
mkdir -p "$CERT_DIR"

# # generate CA key
openssl genrsa -out "${CERT_DIR}/ca.key" 4096
# generate CA cert
openssl req -x509 -new -nodes -key "${CERT_DIR}/ca.key" -sha256 -days 365 \
    -out "${CERT_DIR}/ca.crt" -subj "$SUBJECT"

# generate server key
openssl genrsa -out "${CERT_DIR}/server.key" 4096
# generate server cert signing request (CSR)
openssl req -new -key "${CERT_DIR}/server.key" -out "${CERT_DIR}/server.csr" \
    -subj "$SUBJECT"

# get lan ip, or default to 127.0.0.1
INTERFACE="eno1"
LAN_IP=$(ip addr show ${INTERFACE} | grep -oP '(?<=inet\s)\d+(\.\d+){3}' | head -n 1)
INTERFACE="eno1"
LAN_IP="${LAN_IP:-$(ip addr show ${INTERFACE} | grep -oP '(?<=inet\s)\d+(\.\d+){3}' | head -n 1)}"
LAN_IP="${LAN_IP:-127.0.0.1}"

# create config file for Subject Alternative Names (SAN)
tee "${CERT_DIR}/server.ext" > /dev/null << EOF
authorityKeyIdentifier=keyid,issuer
basicConstraints=CA:FALSE
keyUsage = digitalSignature, nonRepudiation, keyEncipherment, dataEncipherment
subjectAltName = @alt_names

[alt_names]
DNS.1 = localhost
IP.1 = 127.0.0.1
EOF

# add additional IPs to SAN
declare -i IP_COUNT=1
for INTERFACE in "${INTERFACES[@]}"; do
    LAN_IP=$(ip addr show ${INTERFACE} | grep -oP '(?<=inet\s)\d+(\.\d+){3}' | head -n 1)
    if [[ -n "$LAN_IP" ]]; then
        IP_COUNT+=1
        echo "IP.${IP_COUNT} = $LAN_IP" >> "${CERT_DIR}/server.ext"
    fi
done

# sign CSR with CA
openssl x509 -req -in "${CERT_DIR}/server.csr" -CA "${CERT_DIR}/ca.crt" \
    -CAkey "${CERT_DIR}/ca.key" -CAcreateserial -out "${CERT_DIR}/server.crt" \
    -days 365 -sha256 -extfile "${CERT_DIR}/server.ext" -subj "$SUBJECT"

echo "[*] saved to cert/server.crt and cert/server.key"
