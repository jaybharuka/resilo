#!/usr/bin/env python3
"""
Network Diagnostics
Check what might be blocking our dashboard connections
"""

import socket
import subprocess
import sys
from datetime import datetime

import psutil


def check_network_diagnostics():
    """Run comprehensive network diagnostics"""
    print("🔍 NETWORK DIAGNOSTICS FOR AIOPS DASHBOARD")
    print("=" * 60)
    print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()
    
    # 1. Check basic network interface
    print("1. 📡 NETWORK INTERFACES:")
    try:
        import socket
        hostname = socket.gethostname()
        ip_address = socket.gethostbyname(hostname)
        print(f"   Hostname: {hostname}")
        print(f"   IP Address: {ip_address}")
        
        # Check localhost specifically
        localhost_ip = socket.gethostbyname('localhost')
        print(f"   Localhost resolves to: {localhost_ip}")
        
    except Exception as e:
        print(f"   ❌ Error getting network info: {e}")
    
    print()
    
    # 2. Check if we can bind to ports
    print("2. 🔌 PORT AVAILABILITY TEST:")
    test_ports = [5000, 5001, 8000, 8001, 8080]
    
    for port in test_ports:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(1)
                result = s.connect_ex(('127.0.0.1', port))
                if result == 0:
                    print(f"   Port {port}: ❌ BUSY (something is listening)")
                else:
                    print(f"   Port {port}: ✅ AVAILABLE")
        except Exception as e:
            print(f"   Port {port}: ❌ ERROR ({e})")
    
    print()
    
    # 3. Test socket binding
    print("3. 🔗 SOCKET BINDING TEST:")
    try:
        test_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        test_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        test_socket.bind(('127.0.0.1', 9999))
        test_socket.listen(1)
        print("   ✅ Can bind to 127.0.0.1:9999")
        test_socket.close()
    except Exception as e:
        print(f"   ❌ Cannot bind to sockets: {e}")
    
    print()
    
    # 4. Check firewall status (Windows)
    print("4. 🛡️ WINDOWS FIREWALL STATUS:")
    try:
        result = subprocess.run(['netsh', 'advfirewall', 'show', 'allprofiles', 'state'], 
                              capture_output=True, text=True, timeout=10)
        if result.returncode == 0:
            lines = result.stdout.split('\n')
            for line in lines:
                if 'State' in line:
                    print(f"   {line.strip()}")
        else:
            print("   ⚠️ Could not check firewall status")
    except Exception as e:
        print(f"   ⚠️ Error checking firewall: {e}")
    
    print()
    
    # 5. Check running processes on common ports
    print("5. 📊 PROCESSES USING COMMON PORTS:")
    try:
        connections = psutil.net_connections(kind='inet')
        port_users = {}
        
        for conn in connections:
            if conn.laddr.port in test_ports and conn.status == 'LISTEN':
                try:
                    proc = psutil.Process(conn.pid)
                    port_users[conn.laddr.port] = proc.name()
                except:
                    port_users[conn.laddr.port] = "Unknown"
        
        if port_users:
            for port, process in port_users.items():
                print(f"   Port {port}: Used by {process}")
        else:
            print("   ✅ No processes using our target ports")
            
    except Exception as e:
        print(f"   ❌ Error checking processes: {e}")
    
    print()
    
    # 6. Python HTTP server test
    print("6. 🐍 PYTHON HTTP SERVER TEST:")
    try:
        from http.server import BaseHTTPRequestHandler, HTTPServer
        
        class TestHandler(BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(200)
                self.send_header('Content-type', 'text/plain')
                self.end_headers()
                self.wfile.write(b'Test successful!')
            
            def log_message(self, format, *args):
                pass  # Suppress logs
        
        # Try to start a test server briefly
        server = HTTPServer(('127.0.0.1', 9998), TestHandler)
        print("   ✅ Python HTTP server can start")
        server.server_close()
        
    except Exception as e:
        print(f"   ❌ Python HTTP server test failed: {e}")
    
    print()

def run_simple_connectivity_test():
    """Run a simple connectivity test"""
    print("7. 🔄 SIMPLE CONNECTIVITY TEST:")
    
    # Test with a minimal server
    try:
        import threading
        import time
        from http.server import BaseHTTPRequestHandler, HTTPServer
        
        class MinimalHandler(BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(200)
                self.send_header('Content-type', 'text/plain')
                self.end_headers()
                self.wfile.write(b'Hello from AIOps!')
            
            def log_message(self, format, *args):
                print(f"   📞 Request: {format % args}")
        
        # Start server in background
        server = HTTPServer(('127.0.0.1', 9997), MinimalHandler)
        server_thread = threading.Thread(target=server.serve_forever, daemon=True)
        server_thread.start()
        
        print("   🚀 Test server started on port 9997")
        
        # Give it a moment to start
        time.sleep(1)
        
        # Test connection
        try:
            import urllib.request
            response = urllib.request.urlopen('http://127.0.0.1:9997/', timeout=5)
            content = response.read().decode()
            print(f"   ✅ Connection successful! Response: {content}")
            
        except Exception as e:
            print(f"   ❌ Connection failed: {e}")
        
        server.shutdown()
        server.server_close()
        
    except Exception as e:
        print(f"   ❌ Test server failed: {e}")

def show_recommendations():
    """Show troubleshooting recommendations"""
    print("\n💡 TROUBLESHOOTING RECOMMENDATIONS:")
    print("=" * 60)
    print()
    
    print("🔧 IF DASHBOARD WON'T START:")
    print("   1. Try different ports (8000, 8080, 3000)")
    print("   2. Run as administrator")
    print("   3. Check Windows Defender/Firewall")
    print("   4. Restart terminal as administrator")
    print()
    
    print("🌐 IF DASHBOARD STARTS BUT NOT ACCESSIBLE:")
    print("   1. Check Windows Firewall exceptions")
    print("   2. Try 0.0.0.0 instead of 127.0.0.1")
    print("   3. Disable antivirus temporarily")
    print("   4. Use different browser")
    print()
    
    print("🚀 ALTERNATIVE SOLUTIONS:")
    print("   1. Use built-in Python http.server module")
    print("   2. Try different Python web framework")
    print("   3. Use standalone executable version")
    print("   4. Run in WSL if available")
    print()
    
    print("📞 IMMEDIATE WORKAROUND:")
    print("   python -m http.server 8000 --directory .")
    print("   (Serves static files from current directory)")

def main():
    """Main diagnostic function"""
    check_network_diagnostics()
    run_simple_connectivity_test()
    show_recommendations()
    
    print("\n🎯 SUMMARY:")
    print("If all tests pass but dashboard still doesn't work,")
    print("the issue is likely Windows Firewall or antivirus blocking connections.")
    print("\n💡 Quick fix: Try running terminal as Administrator")

if __name__ == "__main__":
    main()