$CertDir = (Join-Path -Path "$PSScriptRoot" -ChildPath cert)
$CAKey = (Join-Path -Path "$CertDir" -ChildPath ca.key)
$CACrt = (Join-Path -Path "$CertDir" -ChildPath ca.crt)
$ServerKey = (Join-Path -Path "$CertDir" -ChildPath server.key)
$ServerCsr = (Join-Path -Path "$CertDir" -ChildPath server.csr)
$ServerExt = (Join-Path -Path "$CertDir" -ChildPath server.ext)
$ServerCrt = (Join-Path -Path "$CertDir" -ChildPath server.crt)
$Cert = (Join-Path -Path "$CertDir" -ChildPath cert.pem)
$Subject = '/C=US/ST=CA/L=SanFrancisco/O=ShareText-LAN'
$Interface = 'Wi-FI'

Write-Output '[*] generating certificates and keys...'

# create cert folder
New-Item -ItemType directory -Force -Path "$CertDir" > $null

# generate CA key
openssl genrsa -out "$CAKey" 4096
# generate CA cert
openssl req -x509 -new -nodes -key "$CAKey" -sha256 -days 365 `
    -out "$CACrt" -subj "$Subject"

# generate server key
openssl genrsa -out "$ServerKey" 4096
# generate server cert signing request (CSR)
openssl req -new -key "$ServerKey" -out "$ServerCsr" -subj "$Subject"

# get lan ip from chosen interface, or default to 127.0.0.1
$LanIP = (Get-NetIPAddress -InterfaceAlias "$Interface" -AddressFamily IPv4 `
        -ErrorAction SilentlyContinue).IPAddress
If (-not $LanIP) { $LanIP = '127.0.0.1' }

# create config file for Subject Alternative Names (SAN)
@"
[v3_req]
authorityKeyIdentifier=keyid,issuer
basicConstraints=CA:FALSE
keyUsage = digitalSignature, nonRepudiation, keyEncipherment, dataEncipherment
subjectAltName = @alt_names

[alt_names]
IP.1 = 127.0.0.1
IP.2 = $LanIP
DNS.1 = localhost
"@ | Out-File -Encoding ascii -FilePath "$ServerExt"

# sign CSR with CA
openssl x509 -req -in "$ServerCsr" -CA "$CACrt" -CAkey "$CAKey" `
    -CAcreateserial -out "$ServerCrt" -days 365 -sha256 `
    -extfile "$ServerExt" -extensions v3_req -subj "$Subject"

Write-Output "[*] saved to cert\server.crt and cert\server.key"
