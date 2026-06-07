#!/usr/bin/env python3
"""
signal_app.py - Aplicación de usuario para TP5 SdeC UNC
Grupo: apache-tevez

Lee el CDD /dev/signal_sensor y sirve los datos via HTTP
para visualización en tiempo real desde el navegador del host.

Uso:
    python3 signal_app.py [puerto]
    
Abrir en el navegador: http://<ip-de-la-vm>:<puerto>
"""

import http.server
import json
import threading
import time
import sys
import os

DEVICE_PATH = "/dev/signal_sensor"
DEFAULT_PORT = 8080

# Buffer circular de datos para el gráfico
MAX_SAMPLES = 60  # Últimos 60 segundos
data_lock = threading.Lock()
signal_data = {
    "current_signal": 0,
    "signal_name": "Senoidal",
    "samples": [],        # Lista de {"time": t, "value": v}
    "start_time": 0,
}


def read_device():
    """Lee un valor del dispositivo de caracteres."""
    try:
        with open(DEVICE_PATH, "r") as f:
            line = f.read().strip()
        # Parsear: SIGNAL=0,VALUE=500,SAMPLE=42
        parts = {}
        for item in line.split(","):
            key, val = item.split("=")
            parts[key] = int(val)
        return parts
    except Exception as e:
        print(f"Error leyendo {DEVICE_PATH}: {e}")
        return None


def write_device(signal_num):
    """Escribe al dispositivo para seleccionar la señal."""
    try:
        with open(DEVICE_PATH, "w") as f:
            f.write(str(signal_num))
        return True
    except Exception as e:
        print(f"Error escribiendo {DEVICE_PATH}: {e}")
        return False


def sensor_thread():
    """Hilo que lee el sensor cada 1 segundo."""
    global signal_data
    
    while True:
        reading = read_device()
        if reading:
            with data_lock:
                elapsed = time.time() - signal_data["start_time"]
                signal_data["samples"].append({
                    "time": round(elapsed, 1),
                    "value": reading["VALUE"],
                    "sample_num": reading["SAMPLE"],
                })
                # Mantener solo los últimos MAX_SAMPLES
                if len(signal_data["samples"]) > MAX_SAMPLES:
                    signal_data["samples"] = signal_data["samples"][-MAX_SAMPLES:]
        time.sleep(1)


# Página HTML con gráfico en tiempo real
HTML_PAGE = """<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>TP5 SdeC - Sensor de Señales (apache-tevez)</title>
<style>
    * { margin: 0; padding: 0; box-sizing: border-box; }
    body { 
        font-family: 'Segoe UI', sans-serif; 
        background: #1a1a2e; 
        color: #e0e0e0; 
        padding: 20px;
    }
    h1 { text-align: center; color: #00d4ff; margin-bottom: 5px; font-size: 1.5em; }
    .subtitle { text-align: center; color: #888; margin-bottom: 20px; font-size: 0.9em; }
    .container { max-width: 900px; margin: 0 auto; }
    .controls {
        display: flex; gap: 15px; justify-content: center;
        margin-bottom: 20px; flex-wrap: wrap;
    }
    .btn {
        padding: 10px 25px; border: 2px solid #00d4ff; background: transparent;
        color: #00d4ff; border-radius: 8px; cursor: pointer; font-size: 1em;
        transition: all 0.3s;
    }
    .btn:hover { background: #00d4ff; color: #1a1a2e; }
    .btn.active { background: #00d4ff; color: #1a1a2e; }
    .info-bar {
        display: flex; justify-content: space-between; margin-bottom: 10px;
        padding: 10px 15px; background: #16213e; border-radius: 8px;
    }
    .info-item { font-size: 0.9em; }
    .info-item span { color: #00d4ff; font-weight: bold; }
    canvas { 
        width: 100%; height: 350px; background: #16213e; 
        border-radius: 8px; display: block;
    }
    .status { text-align: center; margin-top: 10px; color: #888; font-size: 0.85em; }
</style>
</head>
<body>
<div class="container">
    <h1>Sensor de Señales - TP5</h1>
    <p class="subtitle">Sistemas de Computación - UNC | Grupo: apache-tevez</p>
    
    <div class="controls">
        <button class="btn active" id="btn-s0" onclick="changeSignal(0)">
            Señal 0: Senoidal
        </button>
        <button class="btn" id="btn-s1" onclick="changeSignal(1)">
            Señal 1: Cuadrada
        </button>
    </div>
    
    <div class="info-bar">
        <div class="info-item">Señal: <span id="info-signal">Senoidal</span></div>
        <div class="info-item">Valor actual: <span id="info-value">--</span></div>
        <div class="info-item">Muestra #: <span id="info-sample">--</span></div>
        <div class="info-item">Unidad: <span id="info-unit">mV</span></div>
    </div>
    
    <canvas id="chart"></canvas>
    <p class="status" id="status">Conectando al sensor...</p>
</div>

<script>
const canvas = document.getElementById('chart');
const ctx = canvas.getContext('2d');
let samples = [];
let currentSignal = 0;
const SIGNAL_NAMES = ['Senoidal', 'Cuadrada'];
const SIGNAL_COLORS = ['#00d4ff', '#ff6b6b'];
const SIGNAL_UNITS = ['mV', 'mV'];

function resizeCanvas() {
    canvas.width = canvas.clientWidth * window.devicePixelRatio;
    canvas.height = canvas.clientHeight * window.devicePixelRatio;
    ctx.scale(window.devicePixelRatio, window.devicePixelRatio);
}
resizeCanvas();
window.addEventListener('resize', resizeCanvas);

function drawChart() {
    const w = canvas.clientWidth;
    const h = canvas.clientHeight;
    const pad = { top: 30, right: 20, bottom: 40, left: 60 };
    const plotW = w - pad.left - pad.right;
    const plotH = h - pad.top - pad.bottom;
    
    ctx.clearRect(0, 0, w, h);
    
    // Título del gráfico
    ctx.fillStyle = SIGNAL_COLORS[currentSignal];
    ctx.font = 'bold 14px Segoe UI, sans-serif';
    ctx.textAlign = 'center';
    ctx.fillText('Señal ' + currentSignal + ': ' + SIGNAL_NAMES[currentSignal], w/2, 20);
    
    // Ejes
    ctx.strokeStyle = '#444';
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(pad.left, pad.top);
    ctx.lineTo(pad.left, pad.top + plotH);
    ctx.lineTo(pad.left + plotW, pad.top + plotH);
    ctx.stroke();
    
    // Labels eje Y (Amplitud en mV)
    ctx.fillStyle = '#888';
    ctx.font = '11px Segoe UI, sans-serif';
    ctx.textAlign = 'right';
    for (let i = 0; i <= 5; i++) {
        let val = (i / 5) * 1000;
        let y = pad.top + plotH - (i / 5) * plotH;
        ctx.fillText(val.toFixed(0) + ' ' + SIGNAL_UNITS[currentSignal], pad.left - 5, y + 4);
        // Grid horizontal
        ctx.strokeStyle = '#2a2a4a';
        ctx.beginPath();
        ctx.moveTo(pad.left, y);
        ctx.lineTo(pad.left + plotW, y);
        ctx.stroke();
    }
    
    // Label eje Y
    ctx.save();
    ctx.translate(15, pad.top + plotH / 2);
    ctx.rotate(-Math.PI / 2);
    ctx.textAlign = 'center';
    ctx.fillStyle = '#888';
    ctx.fillText('Amplitud (' + SIGNAL_UNITS[currentSignal] + ')', 0, 0);
    ctx.restore();
    
    // Label eje X
    ctx.fillStyle = '#888';
    ctx.textAlign = 'center';
    ctx.fillText('Tiempo (s)', pad.left + plotW / 2, h - 5);
    
    if (samples.length < 2) return;
    
    // Labels eje X (tiempo)
    let tMin = samples[0].time;
    let tMax = samples[samples.length - 1].time;
    let tRange = tMax - tMin || 1;
    
    ctx.textAlign = 'center';
    for (let i = 0; i < samples.length; i += Math.max(1, Math.floor(samples.length / 8))) {
        let x = pad.left + ((samples[i].time - tMin) / tRange) * plotW;
        ctx.fillText(samples[i].time.toFixed(0) + 's', x, pad.top + plotH + 20);
    }
    
    // Dibujar señal
    ctx.strokeStyle = SIGNAL_COLORS[currentSignal];
    ctx.lineWidth = 2.5;
    ctx.lineJoin = 'round';
    ctx.beginPath();
    
    for (let i = 0; i < samples.length; i++) {
        let x = pad.left + ((samples[i].time - tMin) / tRange) * plotW;
        let y = pad.top + plotH - (samples[i].value / 1000) * plotH;
        if (i === 0) ctx.moveTo(x, y);
        else ctx.lineTo(x, y);
    }
    ctx.stroke();
    
    // Puntos
    ctx.fillStyle = SIGNAL_COLORS[currentSignal];
    for (let i = 0; i < samples.length; i++) {
        let x = pad.left + ((samples[i].time - tMin) / tRange) * plotW;
        let y = pad.top + plotH - (samples[i].value / 1000) * plotH;
        ctx.beginPath();
        ctx.arc(x, y, 3, 0, Math.PI * 2);
        ctx.fill();
    }
}

async function fetchData() {
    try {
        const res = await fetch('/api/data');
        const data = await res.json();
        samples = data.samples;
        currentSignal = data.current_signal;
        
        // Actualizar info
        document.getElementById('info-signal').textContent = SIGNAL_NAMES[currentSignal];
        document.getElementById('info-unit').textContent = SIGNAL_UNITS[currentSignal];
        if (samples.length > 0) {
            let last = samples[samples.length - 1];
            document.getElementById('info-value').textContent = last.value + ' ' + SIGNAL_UNITS[currentSignal];
            document.getElementById('info-sample').textContent = last.sample_num;
        }
        
        // Actualizar botones
        document.getElementById('btn-s0').className = 'btn' + (currentSignal === 0 ? ' active' : '');
        document.getElementById('btn-s1').className = 'btn' + (currentSignal === 1 ? ' active' : '');
        
        document.getElementById('status').textContent = 
            'Conectado | ' + samples.length + ' muestras | Actualización cada 1s';
        
        drawChart();
    } catch (e) {
        document.getElementById('status').textContent = 'Error de conexión: ' + e.message;
    }
}

async function changeSignal(num) {
    try {
        await fetch('/api/signal', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({signal: num})
        });
        samples = [];  // Reset del gráfico al cambiar señal
        fetchData();
    } catch (e) {
        console.error('Error cambiando señal:', e);
    }
}

// Actualizar cada 1 segundo
setInterval(fetchData, 1000);
fetchData();
</script>
</body>
</html>
"""


class SignalHandler(http.server.BaseHTTPRequestHandler):
    """HTTP Request Handler para la app de señales."""
    
    def log_message(self, format, *args):
        """Reducir el logging."""
        pass
    
    def do_GET(self):
        if self.path == '/':
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.end_headers()
            self.wfile.write(HTML_PAGE.encode('utf-8'))
        
        elif self.path == '/api/data':
            with data_lock:
                response = json.dumps(signal_data)
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(response.encode())
        
        else:
            self.send_error(404)
    
    def do_POST(self):
        if self.path == '/api/signal':
            content_len = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(content_len)
            
            try:
                data = json.loads(body)
                new_signal = int(data.get('signal', 0))
                
                if new_signal not in (0, 1):
                    raise ValueError("Señal debe ser 0 o 1")
                
                # Escribir al dispositivo
                write_device(new_signal)
                
                # Resetear datos al cambiar señal
                with data_lock:
                    signal_data["current_signal"] = new_signal
                    signal_data["signal_name"] = "Senoidal" if new_signal == 0 else "Cuadrada"
                    signal_data["samples"] = []
                    signal_data["start_time"] = time.time()
                
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({"ok": True}).encode())
                
                print(f"[APP] Señal cambiada a {new_signal} "
                      f"({'Senoidal' if new_signal == 0 else 'Cuadrada'})")
            
            except Exception as e:
                self.send_response(400)
                self.end_headers()
                self.wfile.write(json.dumps({"error": str(e)}).encode())
        else:
            self.send_error(404)


def main():
    port = int(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_PORT
    
    # Verificar acceso al dispositivo
    if not os.path.exists(DEVICE_PATH):
        print(f"[ERROR] No se encuentra {DEVICE_PATH}")
        print("        ¿Está cargado el módulo? -> sudo insmod signal_driver.ko")
        sys.exit(1)
    
    # Inicializar datos
    signal_data["start_time"] = time.time()
    
    # Iniciar hilo de lectura del sensor
    t = threading.Thread(target=sensor_thread, daemon=True)
    t.start()
    print(f"[APP] Leyendo sensor desde {DEVICE_PATH}")
    
    # Iniciar servidor HTTP
    server = http.server.HTTPServer(('0.0.0.0', port), SignalHandler)
    print(f"[APP] Servidor web en http://0.0.0.0:{port}")
    print(f"[APP] Abrir en el navegador del host: http://localhost:{port}")
    print(f"[APP] Presionar Ctrl+C para detener")
    
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[APP] Detenido.")
        server.server_close()


if __name__ == "__main__":
    main()
