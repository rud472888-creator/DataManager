export function connectEvents({ token, onEvent, onStatusChange, onError }) {
  const protocol = window.location.protocol === "https:" ? "wss" : "ws";
  const socket = new WebSocket(
    `${protocol}://${window.location.host}/ws/events?token=${encodeURIComponent(token)}`
  );
  onStatusChange?.("connecting");
  socket.addEventListener("open", () => onStatusChange?.("connected"));
  socket.addEventListener("message", (message) => {
    try {
      onEvent?.(JSON.parse(message.data));
    } catch (error) {
      onError?.(error);
    }
  });
  socket.addEventListener("close", () => onStatusChange?.("closed"));
  socket.addEventListener("error", () => {
    onStatusChange?.("error");
    onError?.(new Error("WebSocket error"));
  });
  return socket;
}
