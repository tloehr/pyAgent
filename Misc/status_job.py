import threading, time, json
import paho.mqtt.client as mqtt
import context
from context import Context
from datetime import datetime
from PagedDisplay import my_lcd
from subprocess import Popen, PIPE
import re

EVERY_MINUTE: int = 60
MQTT_STATUS: str = "/status"


class StatusJob(threading.Thread):
    def __init__(self, mqtt_client: mqtt.Client, my_context: Context):
        self.__mqtt_client = mqtt_client
        self.__my_context = my_context
        threading.Thread.__init__(self)
        self.start()

    def run(self):
        self.__my_context.log.debug("Status Job starting")
        while True:
            self.send_status()
            time.sleep(EVERY_MINUTE)

    def send_status(self):
        if not self.__mqtt_client.is_connected():
            self.__my_context.log.debug("mqtt client is not connected. skipping status()")
            return
        wifi_info: (int, str, str) = context.get_current_wifi_signal_strength()

        this_status = {"version": f"pyAgent {my_lcd.AGVERSION}b{my_lcd.AGBUILD}",
                       "reconnects": self.__my_context.num_of_reconnects - 1,
                       "mqtt-broker": self.__my_context.mqtt_broker,
                       "failed_pings": 0,
                       "ip": self.__my_context.IPADDRESS,
                       "essid": wifi_info[2],
                       "wifi": wifi_info[1],
                       "timestamp": datetime.now().isoformat()
                       }
        # self.__check_signal_strength()
        self.__mqtt_client.publish(self.__my_context.MQTT_OUTBOUND + MQTT_STATUS, json.dumps(this_status),
                                   self.__my_context.MQTT_STATUS_QOS, False)


"""
             public static void check_iwconfig(HashMap<String, String> current_network_values, String iwconfig_output) {
                    if (!Tools.isArm()) {
                        // a regular desktop has always good connection
                        current_network_values.put("essid", "!DESKTOP!");
                        current_network_values.put("ap", "00223F97A198");
                        current_network_values.put("bitrate", "--");
                        current_network_values.put("txpower", "--");
                        current_network_values.put("link", "--");
                        current_network_values.put("freq", "--");
                        current_network_values.put("powermgt", "--");
                        current_network_values.put("signal", Integer.toString(WIFI_PERFECT));
                        return;
                    }
            
                    iwconfig_output = iwconfig_output.replaceAll("\n|\r|\"", "");
            
                    List<String> l = Collections.list(new StringTokenizer(iwconfig_output, " :="))
                            .stream().map(token -> (String) token).collect(Collectors.toList());
                    current_network_values.put("essid", l.contains("ESSID") ? l.get(l.indexOf("ESSID") + 1) : "--");
                    if (l.contains("Point")) {
                        final int index = l.indexOf("Point");
                        if (l.get(index + 1).equalsIgnoreCase("Not-Associated")) {
                            current_network_values.put("ap", "Not-Associated");
                        } else {
                            // reconstruct MAC Address
                            String mac = "";
                            for (int i = 1; i < 7; i++) {
                                mac += l.get(index + i);
                            }
                            current_network_values.put("ap", mac);
                        }
                    }
            
                    current_network_values.put("bitrate", l.contains("Bit") ? l.get(l.indexOf("Bit") + 2) : "--");
                    current_network_values.put("txpower", l.contains("Tx-Power") ? l.get(l.indexOf("Tx-Power") + 1) : "--");
                    current_network_values.put("link", l.contains("Quality") ? l.get(l.indexOf("Quality") + 1) : "--");
                    current_network_values.put("freq", l.contains("Frequency") ? l.get(l.indexOf("Frequency") + 1) : "--");
                    current_network_values.put("powermgt", l.contains("Management") ? l.get(l.indexOf("Management") + 1) : "--");
                    current_network_values.put("signal", l.contains("Signal") ? l.get(l.indexOf("Signal") + 2) : "--");
                }
            
            
                public static String getIWConfig(String cmd) {
                    // this is a result from a non connected raspi
                    // just for test reasons. Is not used in any way.
                    if (!Tools.isArm()) return "wlan0     unassociated  Nickname:\"rtl_wifi\"\n" +
                            "          Mode:Managed  Access Point: Not-Associated   Sensitivity:0/0\n" +
                            "          Retry:off   RTS thr:off   Fragment thr:off\n" +
                            "          Power Management:off\n" +
                            "          Link Quality:0  Signal level:0  Noise level:0\n" +
                            "          Rx invalid nwid:0  Rx invalid crypt:0  Rx invalid frag:0\n" +
                            "          Tx excessive retries:0  Invalid misc:0   Missed beacon:0";
            
                    String result = "error";
            
                    try {
                        ProcessBuilder processBuilder = new ProcessBuilder();
                        processBuilder.command("bash", "-c", cmd);
            
                        Process process = processBuilder.start();
                        StringBuilder output = new StringBuilder();
                        BufferedReader reader = new BufferedReader(new InputStreamReader(process.getInputStream()));
            
                        String line;
                        while ((line = reader.readLine()) != null) {
                            output.append(line + "\n");
                        }
            
                        int exitVal = process.waitFor();
                        if (exitVal == 0) {
                            log.trace("command {} returned \n\n {} ", cmd, output);
                            result = output.toString();
                        }
                    } catch (IOException | InterruptedException io) {
                        log.error(io);
                    }
                    return result;
                }"""
