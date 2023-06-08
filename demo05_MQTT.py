# send T/H sensor data to MQTT cloud platform
# control light with MQTT

from umqtt.simple import MQTTClient
from machine import Pin
import dht
import ubinascii
import machine
import network
import time
import os
import json
import ntptime

# ESP8266 ESP-12 modules have blue, active-low LED on GPIO2
led = Pin(2, Pin.OUT, value=1)
relay = Pin(5, Pin.OUT, value=1)
my_new_msg = None
TOPIC_BASE = 'malo-iot'

#Control Function
def led_onoff(onoff):
    """ control led ON or OFF
        parameter:
        onoff
            0-->ON, 1-->OFF (acturely, led ON when level=0)
    """
    global led
    
    if(onoff==1):
        led.value(0)
    elif(onoff==-1):
        led.value(not led.value())
    else:
        led.value(1)

def dht_get():
    ''' get dht11 sensor's value (T, H)
        return:
            (Temperature, Humidity)
    '''
    T=None
    H=None
    try:
        dht11 = dht.DHT11(Pin(5)) #D1

        dht11.measure()
        T = dht11.temperature()
        H = dht11.humidity()
    except Exception as e:
        print('dht_get error:', str(e))
    
    return T, H

    
def sub_cb(topic, msg):
    global my_new_msg
    global TOPIC_BASE
    topic_light = TOPIC_BASE+"/light"
    topic_t = TOPIC_BASE+'/T'
    topic_h = TOPIC_BASE+'/H'

    topic = topic.decode('utf-8')
    msg = msg.decode('utf-8')
    my_new_msg = '['+topic+'] '+ msg
    print(my_new_msg)
    
    if(topic == topic_light):
        if msg == "0":
            led_onoff(0)
            relay.value(0)
        else:
            led_onoff(1)
            relay.value(1)
    if(topic == topic_t):
        pass
    if(topic == topic_h):
        pass

def read_config():
    config_data = {}
    try:
        f = open('config.txt')
        data = f.read()
        f.close()
        config_data = json.loads(data)
    except Exception as e:
        print('ex: ', str(e))

    return config_data

def write_config(config_data={}):
    try:
        data = json.dumps(config_data)
        f = open('config.txt', 'w')
        f.write(data)
        f.close()
    except Exception as e:
        print('ex: ', str(e))

def get_tw_time(is_hhmm=False):
    utc_epoch=time.mktime(time.localtime()) #utc_epoch
    YY,MM,DD,hh,mm,ss,wday,yday=time.localtime(utc_epoch+28800)
    if is_hhmm:
        hhmm = '%02d%02d' %(hh, mm)
        return hhmm

    return (YY,MM,DD,hh,mm,ss)
    
def main():
    global my_new_msg
    global TOPIC_BASE
    
    mq_fail_count = 0
    tm_pub_th = time.ticks_ms()
    tm_ntp = time.ticks_ms()
    tm_relay = time.ticks_ms()

    led_onoff(1)

    # make default config for test
    #config_data = {'on_time':['1154', '1156', '1158', '1200'], 'off_time':['1155', '1157', '1159', '1201']}
    on_time = []
    off_time = []
    for i in range(0, 60, 2):
        on_time.append('13%02d' %(i))
    for i in range(1, 60, 2):
        off_time.append('13%02d' %(i))
    config_data = {'on_time':on_time, 'off_time':off_time}
    write_config(config_data)
    # read config
    config = read_config()
    print('config:', config)
    # ntp-time-fix, and show tw-time
    try:
        ntptime.settime()
    except Exception as e:
        print('ex: ', str(e))
    print('tw_time: ', get_tw_time())

    # Default MQTT server to connect to
    server = "broker.hivemq.com"
    CLIENT_ID = ubinascii.hexlify(machine.unique_id()).decode('utf-8')
    topic_light = TOPIC_BASE+"/light"
    topic_t = TOPIC_BASE+'/T'
    topic_h = TOPIC_BASE+'/H'
    topic_msg = TOPIC_BASE+'/msg'
    

    wlan = network.WLAN(network.STA_IF)
    print('connecting to AP')
    while(not wlan.isconnected()):
        print(wlan.ifconfig())
        time.sleep(0.1)
        led_onoff(-1)
    print('connected!  --> ', wlan.ifconfig())

    c = MQTTClient(CLIENT_ID, server)
    # Subscribed messages will be delivered to this callback
    c.set_callback(sub_cb)
    c.connect()
    c.subscribe(topic_light)
    print("Connected to %s, subscribed to %s topic" % (server, topic_light))

    # wifi ready, blink led
    for i in range(3):
        led_onoff(1)
        time.sleep(1)
        led_onoff(0)
        time.sleep(1)
    print('I am ready!, ID='+str(CLIENT_ID))
    c.publish(topic_msg, 'I am ready!, ID='+str(CLIENT_ID))

    try:
        while 1:

            #1>control relay
            try:
                if(time.ticks_ms()-tm_relay > 5000): # 5 sec.
                    tm_relay = time.ticks_ms()

                    #check on off
                    my_time = get_tw_time()
                    hhmm = '%02d%02d' %(my_time[3], my_time[4])
                    if hhmm in config['on_time']:
                        relay.value(1)
                        print('turn on @ %s' %(hhmm))
                    if hhmm in config['off_time']:
                        relay.value(0)
                        print('turn off @ %s' %(hhmm))

            except Exception as e:
                print('ex: ', str(e))
                time.sleep(1)

            #2>check wlan
            if(not wlan.isconnected()):
                # not do any mq operation
                time.sleep(0.1)
                led_onoff(-1)                
                continue
            
            try:
                #c.wait_msg()
                c.check_msg()
                if my_new_msg:
                    c.publish(topic_msg, my_new_msg)
                    my_new_msg = None

                if(time.ticks_ms()-tm_ntp > 60000): # 600 sec
                    tm_ntp = time.ticks_ms()
                    try:
                        ntptime.settime()
                    except Exception as e:
                        print('ex: ', str(e))
                    print('tw_time: ', get_tw_time())

            except Exception as e:
                print('wlan:', wlan.isconnected())
                print('ex: ', str(e))
                mq_fail_count+=1
                time.sleep(1)
                
            try:
                if mq_fail_count>5:
                    mq_fail_count=0
                    c = MQTTClient(CLIENT_ID, server)
                    # Subscribed messages will be delivered to this callback
                    c.set_callback(sub_cb)
                    c.connect()
                    c.subscribe(topic_light)
                    print("Connected to %s, subscribed to %s topic" % (server, topic_light))
            except Exception as e:
                print('wlan:', wlan.isconnected())
                print('ex: ', str(e))
                    

            time.sleep(0.001)
                        
    finally:
        c.disconnect()


if __name__ == '__main__':
    main()
