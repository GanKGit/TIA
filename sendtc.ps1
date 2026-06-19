param(
    [Parameter(Mandatory=$true)]
    [string]$IP,

    [Parameter(Mandatory=$true)]
    [int]$Port
)

$client = $null
$stream = $null

try {
    $client = New-Object System.Net.Sockets.TcpClient
    $client.Connect($IP, $Port)
    $stream = $client.GetStream()

    Write-Host "Connected to $IP`:$Port"
    Write-Host "Type message and press Enter. Press Ctrl+C to exit."

    while ($true) {
        $msg = Read-Host
        $bytes = [System.Text.Encoding]::UTF8.GetBytes($msg + "`n")
        $stream.Write($bytes, 0, $bytes.Length)

        Start-Sleep -Milliseconds 100

        while ($stream.DataAvailable) {
            $buffer = New-Object byte[] 4096
            $count = $stream.Read($buffer, 0, $buffer.Length)
            if ($count -gt 0) {
                $response = [System.Text.Encoding]::UTF8.GetString($buffer, 0, $count)
                Write-Host $response
            }
        }
    }
}
catch {
    Write-Host "Error: $($_.Exception.Message)"
}
finally {
    if ($stream) { $stream.Close() }
    if ($client) { $client.Close() }
}
