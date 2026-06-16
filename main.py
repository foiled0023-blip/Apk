# BedrockBridge
# A free Python/Kivy Bedrock LAN relay prototype.
# Put your real Bedrock/Geyser server IP in the app, press START, then check LAN/Friends on console.

import argparse
import random
import socket
import struct
import sys
import threading
import time
import traceback
from queue import Queue, Empty

MAGIC = bytes.fromhex("00ffff00fefefefefdfdfdfd12345678")
DEFAULT_BEDROCK_PORT = 19132


def now_ms():
    return int(time.time() * 1000)


def log_safe(log_fn, msg):
    try:
        log_fn(str(msg))
    except Exception:
        pass


def split_host_port(host_text, default_port=DEFAULT_BEDROCK_PORT):
    host_text = (host_text or "").strip()
    host_text = host_text.replace("https://", "").replace("http://", "")
    host_text = host_text.split("/")[0].strip()

    # IPv6 literal support is not the goal here; Bedrock LAN bridge should use IPv4.
    if ":" in host_text:
        host, port = host_text.rsplit(":", 1)
        if port.isdigit():
            return host.strip(), int(port)

    return host_text, int(default_port)


def is_unconnected_ping(data: bytes) -> bool:
    return len(data) >= 25 and data[0] == 0x01 and MAGIC in data


def build_ping():
    guid = random.getrandbits(63)
    return b"\x01" + struct.pack(">Q", now_ms()) + MAGIC + struct.pack(">Q", guid)


def parse_pong_motd(data: bytes):
    # RakNet unconnected pong:
    # 0x1c | ping time 8 | server guid 8 | magic 16 | string length 2 | motd
    if len(data) < 35 or data[0] != 0x1C:
        return None
    if data[17:33] != MAGIC:
        return None
    strlen = struct.unpack(">H", data[33:35])[0]
    motd = data[35:35 + strlen]
    return motd if motd else None


def query_remote_motd(host, port, timeout=3.0):
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.settimeout(timeout)
    try:
        s.sendto(build_ping(), (host, int(port)))
        data, _ = s.recvfrom(4096)
        return parse_pong_motd(data)
    finally:
        s.close()


def fallback_motd(server_guid):
    # Version/protocol may not match your exact Minecraft version if remote status cannot be read.
    text = (
        f"MCPE;BedrockBridge;800;1.21.x;0;20;{server_guid};"
        f"Python LAN Relay;Survival;1;19132;19132;"
    )
    return text.encode("utf-8")


def build_pong(ping_packet: bytes, server_guid: int, motd_bytes: bytes):
    ping_time = ping_packet[1:9] if len(ping_packet) >= 9 else struct.pack(">Q", now_ms())
    motd_bytes = motd_bytes[:65000]
    return (
        b"\x1c"
        + ping_time
        + struct.pack(">Q", server_guid)
        + MAGIC
        + struct.pack(">H", len(motd_bytes))
        + motd_bytes
    )


class ClientRelay:
    def __init__(self, parent, client_addr):
        self.parent = parent
        self.client_addr = client_addr
        self.last_seen = time.time()
        self.running = True

        self.remote_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.remote_sock.settimeout(1.0)
        self.remote_sock.connect(parent.remote_addr)

        self.thread = threading.Thread(target=self.remote_loop, daemon=True)
        self.thread.start()

    def send_to_remote(self, data):
        self.last_seen = time.time()
        self.remote_sock.send(data)

    def remote_loop(self):
        log_safe(self.parent.log, f"Relay opened for {self.client_addr[0]}:{self.client_addr[1]}")
        while self.running and self.parent.running:
            try:
                data = self.remote_sock.recv(65535)
                if data:
                    self.parent.local_sock.sendto(data, self.client_addr)
            except socket.timeout:
                continue
            except OSError:
                break
            except Exception as e:
                log_safe(self.parent.log, f"Relay error: {e}")
                break
        self.close()

    def close(self):
        self.running = False
        try:
            self.remote_sock.close()
        except Exception:
            pass


class BedrockBridge:
    def __init__(self, remote_host, remote_port=19132, listen_port=19132, log=print):
        self.remote_host = remote_host.strip()
        self.remote_port = int(remote_port)
        self.listen_port = int(listen_port)
        self.log = log

        self.running = False
        self.local_sock = None
        self.remote_addr = None
        self.server_guid = random.getrandbits(63)
        self.motd_bytes = fallback_motd(self.server_guid)

        self.clients = {}
        self.clients_lock = threading.Lock()

    def start(self):
        if self.running:
            return
        if not self.remote_host:
            raise ValueError("Server IP/domain is empty.")

        self.remote_addr = socket.getaddrinfo(
            self.remote_host,
            self.remote_port,
            socket.AF_INET,
            socket.SOCK_DGRAM
        )[0][4]

        self.running = True
        self.refresh_status()

        self.local_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.local_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.local_sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        self.local_sock.settimeout(1.0)

        try:
            self.local_sock.bind(("0.0.0.0", self.listen_port))
        except PermissionError:
            self.running = False
            raise PermissionError(
                f"Cannot bind UDP port {self.listen_port}. On Android, close other relay apps. "
                f"On Windows, your Bedrock/Geyser server is probably already using it."
            )
        except OSError as e:
            self.running = False
            raise OSError(f"Cannot bind UDP port {self.listen_port}: {e}")

        threading.Thread(target=self.local_loop, daemon=True).start()
        threading.Thread(target=self.status_loop, daemon=True).start()
        threading.Thread(target=self.cleanup_loop, daemon=True).start()

        log_safe(self.log, "Started BedrockBridge")
        log_safe(self.log, f"Listening on UDP 0.0.0.0:{self.listen_port}")
        log_safe(self.log, f"Forwarding to {self.remote_addr[0]}:{self.remote_addr[1]}")
        log_safe(self.log, "Open Minecraft on console and check Friends/LAN Games.")

    def stop(self):
        self.running = False
        with self.clients_lock:
            for relay in list(self.clients.values()):
                relay.close()
            self.clients.clear()
        try:
            if self.local_sock:
                self.local_sock.close()
        except Exception:
            pass
        log_safe(self.log, "Stopped BedrockBridge")

    def refresh_status(self):
        try:
            host = self.remote_addr[0] if self.remote_addr else self.remote_host
            motd = query_remote_motd(host, self.remote_port)
            if motd:
                self.motd_bytes = motd
                decoded = motd.decode("utf-8", errors="replace")
                log_safe(self.log, f"Remote status: {decoded}")
            else:
                log_safe(self.log, "Could not read remote MOTD, using fallback.")
        except Exception as e:
            log_safe(self.log, f"Status query failed: {e}")
            self.motd_bytes = fallback_motd(self.server_guid)

    def status_loop(self):
        while self.running:
            time.sleep(30)
            if self.running:
                self.refresh_status()

    def cleanup_loop(self):
        while self.running:
            time.sleep(10)
            cutoff = time.time() - 60
            with self.clients_lock:
                stale = [addr for addr, relay in self.clients.items() if relay.last_seen < cutoff]
                for addr in stale:
                    self.clients[addr].close()
                    del self.clients[addr]
                    log_safe(self.log, f"Cleaned old relay {addr[0]}:{addr[1]}")

    def get_relay(self, client_addr):
        with self.clients_lock:
            relay = self.clients.get(client_addr)
            if relay is None:
                relay = ClientRelay(self, client_addr)
                self.clients[client_addr] = relay
            return relay

    def local_loop(self):
        while self.running:
            try:
                data, client_addr = self.local_sock.recvfrom(65535)
                if not data:
                    continue

                if is_unconnected_ping(data):
                    pong = build_pong(data, self.server_guid, self.motd_bytes)
                    self.local_sock.sendto(pong, client_addr)
                    continue

                relay = self.get_relay(client_addr)
                relay.send_to_remote(data)

            except socket.timeout:
                continue
            except OSError:
                break
            except Exception as e:
                log_safe(self.log, f"Local loop error: {e}")
                log_safe(self.log, traceback.format_exc())


def try_android_multicast_lock(log_fn):
    try:
        from jnius import autoclass
        PythonActivity = autoclass("org.kivy.android.PythonActivity")
        Context = autoclass("android.content.Context")
        activity = PythonActivity.mActivity
        wifi = activity.getApplicationContext().getSystemService(Context.WIFI_SERVICE)
        lock = wifi.createMulticastLock("BedrockBridgeLock")
        lock.setReferenceCounted(True)
        lock.acquire()
        log_safe(log_fn, "Android Wi-Fi multicast lock acquired.")
        return lock
    except Exception:
        return None


def run_cli():
    parser = argparse.ArgumentParser()
    parser.add_argument("host", help="Bedrock server IP/domain. Example: 192.168.0.50 or play.example.net:19132")
    parser.add_argument("--port", type=int, default=19132)
    parser.add_argument("--listen", type=int, default=19132)
    args = parser.parse_args()
    host, port = split_host_port(args.host, args.port)
    bridge = BedrockBridge(host, port, args.listen, log=print)
    try:
        bridge.start()
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        bridge.stop()


def run_kivy_app():
    from kivy.app import App
    from kivy.clock import Clock
    from kivy.uix.boxlayout import BoxLayout
    from kivy.uix.label import Label
    from kivy.uix.button import Button
    from kivy.uix.textinput import TextInput
    from kivy.uix.scrollview import ScrollView

    class BedrockBridgeApp(App):
        def build(self):
            self.title = "BedrockBridge"
            self.log_queue = Queue()
            self.bridge = None
            self.android_lock = try_android_multicast_lock(self.add_log)

            root = BoxLayout(orientation="vertical", padding=14, spacing=10)

            root.add_widget(Label(
                text="[b]BedrockBridge[/b]\nFree Bedrock LAN relay",
                markup=True,
                size_hint_y=None,
                height=76
            ))

            self.host_input = TextInput(
                hint_text="Server IP/domain, e.g. 192.168.0.50 or play.example.net:19132",
                multiline=False,
                size_hint_y=None,
                height=54
            )
            root.add_widget(self.host_input)

            self.port_input = TextInput(
                text="19132",
                hint_text="Real server port",
                multiline=False,
                input_filter="int",
                size_hint_y=None,
                height=54
            )
            root.add_widget(self.port_input)

            self.listen_input = TextInput(
                text="19132",
                hint_text="Local LAN port, usually 19132",
                multiline=False,
                input_filter="int",
                size_hint_y=None,
                height=54
            )
            root.add_widget(self.listen_input)

            self.start_button = Button(text="START", size_hint_y=None, height=62)
            self.start_button.bind(on_press=self.toggle_bridge)
            root.add_widget(self.start_button)

            self.log_label = Label(
                text="Put your server IP and press START.\nFor your own PC server, use the PC LAN IP, not 127.0.0.1.",
                markup=False,
                size_hint_y=None,
                halign="left",
                valign="top"
            )
            self.log_label.bind(texture_size=self.update_log_height)
            scroll = ScrollView()
            scroll.add_widget(self.log_label)
            root.add_widget(scroll)

            Clock.schedule_interval(self.flush_logs, 0.25)
            return root

        def update_log_height(self, *_):
            self.log_label.height = max(self.log_label.texture_size[1] + 30, 300)
            self.log_label.text_size = (self.log_label.width, None)

        def add_log(self, msg):
            self.log_queue.put(str(msg))

        def flush_logs(self, *_):
            lines = self.log_label.text.splitlines()
            changed = False
            while True:
                try:
                    lines.append(self.log_queue.get_nowait())
                    changed = True
                except Empty:
                    break
            if changed:
                self.log_label.text = "\n".join(lines[-140:])

        def toggle_bridge(self, *_):
            if self.bridge and self.bridge.running:
                self.bridge.stop()
                self.start_button.text = "START"
                return

            raw_host = self.host_input.text.strip()
            if not raw_host:
                self.add_log("Put a server IP/domain first.")
                return

            try:
                fallback_port = int(self.port_input.text or "19132")
                host, parsed_port = split_host_port(raw_host, fallback_port)
                port = parsed_port
                listen = int(self.listen_input.text or "19132")
                self.bridge = BedrockBridge(host, port, listen, log=self.add_log)
                self.bridge.start()
                self.start_button.text = "STOP"
            except Exception as e:
                self.add_log(f"Start failed: {e}")

        def on_stop(self):
            if self.bridge:
                self.bridge.stop()
            try:
                if self.android_lock:
                    self.android_lock.release()
            except Exception:
                pass

    BedrockBridgeApp().run()


if __name__ == "__main__":
    if "--cli" in sys.argv:
        sys.argv.remove("--cli")
        run_cli()
    else:
        try:
            run_kivy_app()
        except ImportError:
            print("Kivy not installed. CLI mode example:")
            print("py main.py --cli 192.168.0.50 --port 19132 --listen 19132")
