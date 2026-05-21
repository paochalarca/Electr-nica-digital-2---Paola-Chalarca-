from machine import Pin, I2C
import network
import time
import math
import dht
import utelegram
import urequests
from mpu6050 import MPU6050

# CONFIGURACION WIFI
SSID = "MILENA"
PASSWORD = "milena0322"

# CONFIGURACION TELEGRAM
TOKEN = "8715805290:AAEecQVxzbacK7siHQ2mFTTGyPECWg6xwME"
CHAT_ID = "6515539982"

# CONFIGURACION SERVIDOR PC
PC_IP = "http://192.168.1.99:5000"

# PINES
BUZZER = Pin(18, Pin.OUT)
BOTON = Pin(19, Pin.IN, Pin.PULL_UP)
INT_MPU = Pin(23, Pin.IN, Pin.PULL_UP)
sensor_dht = dht.DHT11(Pin(4))
i2c = I2C(0, scl=Pin(22), sda=Pin(21))
mpu = MPU6050(i2c)

# UMBRALES
TEMP_MAX = 30
TEMP_MIN = 18
HUM_MAX = 80
HUM_MIN = 30
MOV_UMBRAL = 1.05

# VARIABLES GLOBALES
temperatura = 0
humedad = 0
movimiento = "Reposo"
panico_activado = False
movimiento_detectado = False
ultimo_sensor = 0
INTERVALO_SENSOR = 1000

# INTERRUPCION BOTON PANICO
def isr_boton(pin):
    global panico_activado
    panico_activado = True

# INTERRUPCION MPU6050
def isr_movimiento(pin):
    global movimiento_detectado
    movimiento_detectado = True

BOTON.irq(trigger=Pin.IRQ_FALLING, handler=isr_boton)
INT_MPU.irq(trigger=Pin.IRQ_FALLING, handler=isr_movimiento)

# CONFIGURAR MPU6050 PARA DETECTAR MOVIMIENTO
def configurar_mpu():
    mpu.i2c.writeto_mem(0x68, 0x1F, bytes([50]))  # ← UMBRAL SUBIDO (era 10)
    mpu.i2c.writeto_mem(0x68, 0x20, bytes([1]))
    mpu.i2c.writeto_mem(0x68, 0x38, bytes([0x40]))
    print("MPU6050 configurado para interrupciones")

# FUNCION WIFI
def conectar_wifi():
    wifi = network.WLAN(network.STA_IF)
    print("\nINICIANDO WIFI")
    wifi.active(True)
    if wifi.isconnected():
        print("WiFi ya conectado")
        return wifi
    print("Conectando a:", SSID)
    wifi.connect(SSID, PASSWORD)
    intentos = 0
    while not wifi.isconnected():
        intentos += 1
        print("Intento:", intentos)
        time.sleep(1)
        if intentos >= 15:
            print("\nERROR DE CONEXION WIFI")
            intentos = 0
    print("\nWIFI CONECTADO")
    print("IP:", wifi.ifconfig()[0])
    return wifi

# TELEGRAM
bot = utelegram.ubot(TOKEN)

def enviar_mensaje_inicio():
    mensaje = (
        "ESP32 conectado correctamente\n\n"
        "COMANDOS DISPONIBLES:\n"
        "/temp -> Temperatura\n"
        "/hum -> Humedad\n"
        "/mov -> Movimiento\n"
        "/all -> Ver todos los datos"
    )
    bot.send(CHAT_ID, mensaje)

# DETECTAR MOVIMIENTO
def detectar_movimiento():
    accel = mpu.read_accel_data()
    ax = accel["x"]
    ay = accel["y"]
    az = accel["z"]
    magnitud = math.sqrt(ax**2 + ay**2 + az**2)
    print("Magnitud:", magnitud)
    if magnitud > MOV_UMBRAL:
        return "Movimiento"
    return "Reposo"

# LEER SENSORES
def leer_sensores():
    global temperatura, humedad, movimiento
    sensor_dht.measure()
    temperatura = sensor_dht.temperature()
    humedad = sensor_dht.humidity()
    movimiento = detectar_movimiento()

# ALERTAS
def verificar_alertas():
    alerta = "Normal"
    buzzer_state = False
    if temperatura > TEMP_MAX:
        alerta = "Temperatura Alta"
        buzzer_state = True
    elif temperatura < TEMP_MIN:
        alerta = "Temperatura Baja"
        buzzer_state = True
    elif humedad > HUM_MAX:
        alerta = "Humedad Alta"
        buzzer_state = True
    elif humedad < HUM_MIN:
        alerta = "Humedad Baja"
        buzzer_state = True
    elif movimiento == "Movimiento":
        alerta = "Movimiento Detectado"
        buzzer_state = True

    if buzzer_state:
        BUZZER.on()
    else:
        BUZZER.off()

    return alerta

# ENVIAR DATOS AL SERVIDOR
def enviar_datos():
    try:
        urequests.post(PC_IP + "/datos", json={
            "temperatura": temperatura,
            "humedad": humedad,
            "movimiento": movimiento,
            "alerta": verificar_alertas()
        }, timeout=3)
    except Exception as e:
        print("Error al enviar datos:", e)

# VERIFICAR BOTON PANICO
def verificar_boton_panico():
    global panico_activado
    if panico_activado:
        print("BOTON DE PANICO ACTIVADO")
        bot.send(CHAT_ID, "ALERTA: BOTON DE PANICO ACTIVADO")
        try:
            urequests.post(PC_IP + "/panico", json={"alerta": "PANICO"}, timeout=3)
        except Exception as e:
            print("Error al enviar alerta de panico:", e)
        BUZZER.on()
        time.sleep(6)
        BUZZER.off()
        panico_activado = False

# VERIFICAR MOVIMIENTO POR INTERRUPCION
def verificar_movimiento_isr():
    global movimiento_detectado, movimiento
    if movimiento_detectado:
        print("MOVIMIENTO DETECTADO POR INTERRUPCION")
        movimiento = "Movimiento"
        BUZZER.on()
        time.sleep(2)
        BUZZER.off()
        movimiento = "Reposo"
        movimiento_detectado = False
        enviar_datos()

# MENSAJES TELEGRAM
def mensajes(message):
    texto = message["message"]["text"]
    print("Mensaje recibido:", texto)
    leer_sensores()
    if texto == "/temp":
        bot.send(CHAT_ID, "Temperatura: {} C".format(temperatura))
    elif texto == "/hum":
        bot.send(CHAT_ID, "Humedad: {} %".format(humedad))
    elif texto == "/mov":
        bot.send(CHAT_ID, "Movimiento: {}".format(movimiento))
    elif texto == "/all":
        datos = (
            "DATOS DEL SISTEMA\n\n"
            "Temperatura: {} C\n"
            "Humedad: {} %\n"
            "Movimiento: {}"
        ).format(temperatura, humedad, movimiento)
        bot.send(CHAT_ID, datos)
    else:
        bot.send(CHAT_ID, "Comando no reconocido")

bot.set_default_handler(mensajes)

# INICIO
wifi = conectar_wifi()
configurar_mpu()
enviar_mensaje_inicio()
leer_sensores()
verificar_alertas()

# LOOP PRINCIPAL
while True:
    try:
        verificar_movimiento_isr()
        verificar_boton_panico()
        bot.read_once()

        ahora = time.ticks_ms()
        if time.ticks_diff(ahora, ultimo_sensor) > INTERVALO_SENSOR:
            leer_sensores()
            alerta = verificar_alertas()
            enviar_datos()
            print("\n------------------------")
            print("Temperatura:", temperatura, "C")
            print("Humedad:", humedad, "%")
            print("Movimiento:", movimiento)
            print("Alerta:", alerta)
            ultimo_sensor = ahora

        time.sleep_ms(50)

    except Exception as e:
        print("ERROR:", e)
        time.sleep_ms(100)