package com.adsterra.phoneagent;

import java.io.BufferedInputStream;
import java.io.ByteArrayOutputStream;
import java.io.EOFException;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.InetAddress;
import java.net.ServerSocket;
import java.net.Socket;
import java.net.SocketException;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.Base64;
import java.util.HashMap;
import java.util.Locale;
import java.util.Map;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/**
 * Lightweight pure-Java RFC 6455 WebSocket server bound strictly to 127.0.0.1.
 * Accepts JSON commands ("ping", "status", "tap", "scroll"/"swipe") over
 * ADB-forwarded localhost TCP without third-party libraries.
 */
public class LocalControlServer {

    public static final int DEFAULT_PORT = 8765;
    private static final String LOOPBACK_HOST = "127.0.0.1";
    private static final String WS_MAGIC_GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11";
    private static final long DEFAULT_TAP_DURATION_MS = 80L;
    private static final long DEFAULT_SCROLL_DURATION_MS = 400L;
    private static final int MAX_FRAME_BYTES = 1024 * 1024;

    private static final Pattern KEY_VAL_PATTERN = Pattern.compile(
            "\"([A-Za-z0-9_]+)\"\\s*:\\s*(?:\"([^\"]*)\"|(-?\\d+(?:\\.\\d+)?)|(true|false|null))"
    );

    public static final class GestureResult {
        public final boolean ok;
        public final String message;

        public GestureResult(boolean ok, String message) {
            this.ok = ok;
            this.message = message == null ? "" : message;
        }
    }

    public static final class StatusResult {
        public final boolean accessibilityConnected;
        public final String details;

        public StatusResult(boolean accessibilityConnected, String details) {
            this.accessibilityConnected = accessibilityConnected;
            this.details = details == null ? "" : details;
        }
    }

    public static final class ParsedCommand {
        public final String cmd;
        public final float x;
        public final float y;
        public final float x1;
        public final float y1;
        public final float x2;
        public final float y2;
        public final long durationMs;
        public final String error;

        private ParsedCommand(
                String cmd,
                float x,
                float y,
                float x1,
                float y1,
                float x2,
                float y2,
                long durationMs,
                String error
        ) {
            this.cmd = cmd;
            this.x = x;
            this.y = y;
            this.x1 = x1;
            this.y1 = y1;
            this.x2 = x2;
            this.y2 = y2;
            this.durationMs = durationMs;
            this.error = error;
        }

        public boolean isValid() {
            return error == null;
        }
    }

    public interface CommandHandler {
        StatusResult onStatus();

        GestureResult onTap(float x, float y, long durationMs);

        GestureResult onScroll(float x1, float y1, float x2, float y2, long durationMs);
    }

    private final int port;
    private final CommandHandler handler;
    private final String authToken;
    private final AtomicBoolean running = new AtomicBoolean(false);
    private volatile ServerSocket serverSocket;
    private Thread acceptThread;
    private ExecutorService clientPool;

    public LocalControlServer(int port, CommandHandler handler) {
        this(port, handler, System.getProperty("phoneagent.token", System.getenv("PHONEAGENT_TOKEN")));
    }

    public LocalControlServer(int port, CommandHandler handler, String authToken) {
        this.port = port > 0 ? port : DEFAULT_PORT;
        this.handler = handler;
        this.authToken = (authToken != null && !authToken.trim().isEmpty()) ? authToken.trim() : null;
    }

    public int getPort() {
        ServerSocket ss = serverSocket;
        return ss != null ? ss.getLocalPort() : port;
    }

    public boolean isRunning() {
        return running.get();
    }

    public synchronized void start() throws IOException {
        if (running.get()) {
            return;
        }
        InetAddress loopback = InetAddress.getByName(LOOPBACK_HOST);
        ServerSocket ss = new ServerSocket(port, 16, loopback);
        ss.setReuseAddress(true);
        this.serverSocket = ss;
        this.running.set(true);
        this.clientPool = Executors.newCachedThreadPool();

        acceptThread = new Thread(this::acceptLoop, "phoneagent-ws-accept");
        acceptThread.setDaemon(true);
        acceptThread.start();
    }

    public synchronized void stop() {
        running.set(false);
        if (serverSocket != null) {
            try {
                serverSocket.close();
            } catch (IOException ignored) {
            }
            serverSocket = null;
        }
        if (clientPool != null) {
            clientPool.shutdownNow();
            clientPool = null;
        }
    }

    private void acceptLoop() {
        while (running.get()) {
            ServerSocket ss = serverSocket;
            if (ss == null || ss.isClosed()) {
                break;
            }
            try {
                Socket client = ss.accept();
                client.setTcpNoDelay(true);
                ExecutorService pool = clientPool;
                if (pool != null && !pool.isShutdown()) {
                    pool.submit(() -> handleClient(client));
                } else {
                    client.close();
                }
            } catch (SocketException e) {
                if (!running.get()) {
                    break;
                }
            } catch (IOException ignored) {
            }
        }
    }

    private void handleClient(Socket socket) {
        try (Socket s = socket) {
            BufferedInputStream in = new BufferedInputStream(s.getInputStream());
            OutputStream out = s.getOutputStream();

            if (!performHandshake(in, out)) {
                return;
            }

            ByteArrayOutputStream fragmented = null;
            while (running.get() && !s.isClosed()) {
                Frame frame = readFrame(in);
                if (frame == null) {
                    break;
                }
                if (frame.opcode == 0x8) { // Close
                    writeFrame(out, 0x8, new byte[0]);
                    break;
                } else if (frame.opcode == 0x9) { // Ping
                    writeFrame(out, 0xA, frame.payload);
                    continue;
                } else if (frame.opcode == 0xA) { // Pong
                    continue;
                }

                byte[] payloadBytes;
                if (frame.opcode == 0x1 && frame.fin) {
                    payloadBytes = frame.payload;
                } else if (frame.opcode == 0x1 && !frame.fin) {
                    fragmented = new ByteArrayOutputStream();
                    fragmented.write(frame.payload);
                    continue;
                } else if (frame.opcode == 0x0 && fragmented != null) {
                    fragmented.write(frame.payload);
                    if (!frame.fin) {
                        continue;
                    }
                    payloadBytes = fragmented.toByteArray();
                    fragmented = null;
                } else {
                    continue;
                }

                String text = new String(payloadBytes, StandardCharsets.UTF_8);
                String responseJson = dispatchJsonCommand(text);
                writeFrame(out, 0x1, responseJson.getBytes(StandardCharsets.UTF_8));
            }
        } catch (IOException ignored) {
        }
    }

    private boolean performHandshake(InputStream in, OutputStream out) throws IOException {
        String headerBlock = readHttpHeaders(in);
        if (headerBlock == null || headerBlock.isEmpty()) {
            return false;
        }

        String[] lines = headerBlock.split("\r\n");
        if (lines.length == 0 || !lines[0].startsWith("GET ")) {
            return false;
        }

        Map<String, String> headers = new HashMap<>();
        for (int i = 1; i < lines.length; i++) {
            int idx = lines[i].indexOf(':');
            if (idx > 0) {
                String k = lines[i].substring(0, idx).trim().toLowerCase(Locale.US);
                String v = lines[i].substring(idx + 1).trim();
                headers.put(k, v);
            }
        }

        String secKey = headers.get("sec-websocket-key");
        if (secKey == null || secKey.isEmpty()) {
            out.write("HTTP/1.1 400 Bad Request\r\nConnection: close\r\n\r\n"
                    .getBytes(StandardCharsets.US_ASCII));
            out.flush();
            return false;
        }

        if (authToken != null && !authToken.isEmpty()) {
            String clientToken = headers.get("x-auth-token");
            if (clientToken == null) {
                String authHdr = headers.get("authorization");
                if (authHdr != null && authHdr.toLowerCase(Locale.US).startsWith("bearer ")) {
                    clientToken = authHdr.substring(7).trim();
                }
            }
            if (clientToken == null && lines.length > 0) {
                String firstLine = lines[0];
                int qIdx = firstLine.indexOf('?');
                int sIdx = firstLine.indexOf(" HTTP/");
                if (qIdx > 0 && sIdx > qIdx) {
                    String query = firstLine.substring(qIdx + 1, sIdx);
                    for (String param : query.split("&")) {
                        String[] pair = param.split("=", 2);
                        if (pair.length == 2 && ("token".equalsIgnoreCase(pair[0]) || "auth_token".equalsIgnoreCase(pair[0]))) {
                            clientToken = pair[1].trim();
                            break;
                        }
                    }
                }
            }
            if (clientToken == null || !clientToken.equals(authToken)) {
                out.write("HTTP/1.1 401 Unauthorized\r\nConnection: close\r\n\r\n"
                        .getBytes(StandardCharsets.US_ASCII));
                out.flush();
                return false;
            }
        }

        String accept;
        try {
            MessageDigest sha1 = MessageDigest.getInstance("SHA-1");
            byte[] digest = sha1.digest((secKey + WS_MAGIC_GUID).getBytes(StandardCharsets.US_ASCII));
            accept = Base64.getEncoder().encodeToString(digest);
        } catch (Exception e) {
            return false;
        }

        String response = "HTTP/1.1 101 Switching Protocols\r\n"
                + "Upgrade: websocket\r\n"
                + "Connection: Upgrade\r\n"
                + "Sec-WebSocket-Accept: " + accept + "\r\n\r\n";
        out.write(response.getBytes(StandardCharsets.US_ASCII));
        out.flush();
        return true;
    }

    private static String readHttpHeaders(InputStream in) throws IOException {
        ByteArrayOutputStream buf = new ByteArrayOutputStream();
        int state = 0;
        while (buf.size() < 16384) {
            int b = in.read();
            if (b == -1) {
                return null;
            }
            buf.write(b);
            if ((state == 0 && b == '\r') || (state == 2 && b == '\r')) {
                state++;
            } else if ((state == 1 && b == '\n') || (state == 3 && b == '\n')) {
                state++;
                if (state == 4) {
                    return buf.toString(StandardCharsets.US_ASCII);
                }
            } else {
                state = (b == '\r') ? 1 : 0;
            }
        }
        return null;
    }

    private static final class Frame {
        final boolean fin;
        final int opcode;
        final byte[] payload;

        Frame(boolean fin, int opcode, byte[] payload) {
            this.fin = fin;
            this.opcode = opcode;
            this.payload = payload;
        }
    }

    private static Frame readFrame(InputStream in) throws IOException {
        int b0 = in.read();
        if (b0 == -1) {
            return null;
        }
        int b1 = in.read();
        if (b1 == -1) {
            throw new EOFException("Truncated frame header");
        }

        boolean fin = (b0 & 0x80) != 0;
        int opcode = b0 & 0x0F;
        boolean masked = (b1 & 0x80) != 0;
        long len = b1 & 0x7F;

        if (len == 126) {
            byte[] ext = readExact(in, 2);
            len = ((ext[0] & 0xFF) << 8) | (ext[1] & 0xFF);
        } else if (len == 127) {
            byte[] ext = readExact(in, 8);
            len = 0;
            for (int i = 0; i < 8; i++) {
                len = (len << 8) | (ext[i] & 0xFF);
            }
        }

        if (len < 0 || len > MAX_FRAME_BYTES) {
            throw new IOException("Frame payload exceeds limit: " + len);
        }

        byte[] maskKey = masked ? readExact(in, 4) : null;
        byte[] payload = readExact(in, (int) len);
        if (maskKey != null) {
            for (int i = 0; i < payload.length; i++) {
                payload[i] = (byte) (payload[i] ^ maskKey[i % 4]);
            }
        }
        return new Frame(fin, opcode, payload);
    }

    private static void writeFrame(OutputStream out, int opcode, byte[] payload) throws IOException {
        int len = payload.length;
        out.write(0x80 | (opcode & 0x0F));
        if (len <= 125) {
            out.write(len);
        } else if (len <= 65535) {
            out.write(126);
            out.write((len >> 8) & 0xFF);
            out.write(len & 0xFF);
        } else {
            out.write(127);
            long l = len;
            for (int i = 7; i >= 0; i--) {
                out.write((int) ((l >> (8 * i)) & 0xFF));
            }
        }
        out.write(payload);
        out.flush();
    }

    private static byte[] readExact(InputStream in, int n) throws IOException {
        byte[] out = new byte[n];
        int off = 0;
        while (off < n) {
            int r = in.read(out, off, n - off);
            if (r == -1) {
                throw new EOFException("Unexpected EOF while reading " + n + " bytes");
            }
            off += r;
        }
        return out;
    }

    public String dispatchJsonCommand(String rawJson) {
        ParsedCommand parsed = parseCommand(rawJson);
        if (!parsed.isValid()) {
            return "{\"ok\":false,\"error\":\"" + escapeJson(parsed.error) + "\"}";
        }

        switch (parsed.cmd) {
            case "ping":
                return "{\"ok\":true,\"cmd\":\"ping\",\"pong\":true,\"ts\":" + System.currentTimeMillis() + "}";
            case "status": {
                StatusResult st = handler != null
                        ? handler.onStatus()
                        : new StatusResult(false, "no_handler");
                return "{\"ok\":true,\"cmd\":\"status\",\"server_running\":" + running.get()
                        + ",\"port\":" + getPort()
                        + ",\"accessibility_connected\":" + st.accessibilityConnected
                        + ",\"details\":\"" + escapeJson(st.details) + "\"}";
            }
            case "tap": {
                if (handler == null) {
                    return "{\"ok\":false,\"cmd\":\"tap\",\"error\":\"no_handler\"}";
                }
                GestureResult res = handler.onTap(parsed.x, parsed.y, parsed.durationMs);
                return "{\"ok\":" + res.ok
                        + ",\"cmd\":\"tap\",\"x\":" + parsed.x
                        + ",\"y\":" + parsed.y
                        + ",\"duration_ms\":" + parsed.durationMs
                        + ",\"message\":\"" + escapeJson(res.message) + "\"}";
            }
            case "scroll": {
                if (handler == null) {
                    return "{\"ok\":false,\"cmd\":\"scroll\",\"error\":\"no_handler\"}";
                }
                GestureResult res = handler.onScroll(
                        parsed.x1, parsed.y1, parsed.x2, parsed.y2, parsed.durationMs
                );
                return "{\"ok\":" + res.ok
                        + ",\"cmd\":\"scroll\",\"x1\":" + parsed.x1
                        + ",\"y1\":" + parsed.y1
                        + ",\"x2\":" + parsed.x2
                        + ",\"y2\":" + parsed.y2
                        + ",\"duration_ms\":" + parsed.durationMs
                        + ",\"message\":\"" + escapeJson(res.message) + "\"}";
            }
            default:
                return "{\"ok\":false,\"error\":\"unsupported_command\"}";
        }
    }

    public static ParsedCommand parseCommand(String rawJson) {
        if (rawJson == null) {
            return new ParsedCommand("", 0, 0, 0, 0, 0, 0, 0, "empty_payload");
        }
        String trimmed = rawJson.trim();
        if (!trimmed.startsWith("{") || !trimmed.endsWith("}")) {
            return new ParsedCommand("", 0, 0, 0, 0, 0, 0, 0, "invalid_json_object");
        }

        Map<String, String> fields = new HashMap<>();
        Matcher matcher = KEY_VAL_PATTERN.matcher(trimmed);
        while (matcher.find()) {
            String key = matcher.group(1);
            String strVal = matcher.group(2);
            String numVal = matcher.group(3);
            String litVal = matcher.group(4);
            if (strVal != null) {
                fields.put(key, strVal);
            } else if (numVal != null) {
                fields.put(key, numVal);
            } else if (litVal != null) {
                fields.put(key, litVal);
            }
        }

        String cmd = fields.get("cmd");
        if (cmd == null || cmd.isEmpty()) {
            return new ParsedCommand("", 0, 0, 0, 0, 0, 0, 0, "missing_cmd");
        }
        String normCmd = cmd.toLowerCase(Locale.US);
        if ("swipe".equals(normCmd)) {
            normCmd = "scroll";
        }

        try {
            if ("ping".equals(normCmd) || "status".equals(normCmd)) {
                return new ParsedCommand(normCmd, 0, 0, 0, 0, 0, 0, 0, null);
            }
            if ("tap".equals(normCmd)) {
                if (!fields.containsKey("x") || !fields.containsKey("y")) {
                    return new ParsedCommand(normCmd, 0, 0, 0, 0, 0, 0, 0, "missing_tap_coordinates");
                }
                float x = Float.parseFloat(fields.get("x"));
                float y = Float.parseFloat(fields.get("y"));
                long dur = fields.containsKey("duration_ms")
                        ? Math.max(1L, (long) Double.parseDouble(fields.get("duration_ms")))
                        : DEFAULT_TAP_DURATION_MS;
                return new ParsedCommand(normCmd, x, y, 0, 0, 0, 0, dur, null);
            }
            if ("scroll".equals(normCmd)) {
                if (!fields.containsKey("x1") || !fields.containsKey("y1")
                        || !fields.containsKey("x2") || !fields.containsKey("y2")) {
                    return new ParsedCommand(normCmd, 0, 0, 0, 0, 0, 0, 0, "missing_scroll_coordinates");
                }
                float x1 = Float.parseFloat(fields.get("x1"));
                float y1 = Float.parseFloat(fields.get("y1"));
                float x2 = Float.parseFloat(fields.get("x2"));
                float y2 = Float.parseFloat(fields.get("y2"));
                long dur = fields.containsKey("duration_ms")
                        ? Math.max(1L, (long) Double.parseDouble(fields.get("duration_ms")))
                        : DEFAULT_SCROLL_DURATION_MS;
                return new ParsedCommand(normCmd, 0, 0, x1, y1, x2, y2, dur, null);
            }
            return new ParsedCommand(normCmd, 0, 0, 0, 0, 0, 0, 0, "unknown_cmd:" + normCmd);
        } catch (NumberFormatException e) {
            return new ParsedCommand(normCmd, 0, 0, 0, 0, 0, 0, 0, "invalid_numeric_param");
        }
    }

    private static String escapeJson(String s) {
        if (s == null) {
            return "";
        }
        return s.replace("\\", "\\\\")
                .replace("\"", "\\\"")
                .replace("\n", "\\n")
                .replace("\r", "\\r");
    }
}
