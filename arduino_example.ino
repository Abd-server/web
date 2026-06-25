/*
 * ═══════════════════════════════════════════════════════════
 *  مثال أردوينو R4 WiFi — إرسال قراءة للمنصة (الحقول الحقيقية)
 * ═══════════════════════════════════════════════════════════
 *  عدّل: WIFI و SERVER_HOST و DEVICE_KEY.
 *  - DEVICE_KEY: انسخه من صفحة الفرن (زر "مفتاح الجهاز").
 *  - أثناء التجربة المحلية ضع IP جهاز الخادم (مثل 192.168.1.20)
 *    وليس localhost. بعد النشر ضع دومين الموقع.
 *
 *  الحقول مطابقة لما يتوقعه الخادم:
 *  c1=الحرارة الحقيقية, i1=الافتراضية, x=الدرجة النهائية,
 *  H=حالة البرنامج(0-5), h=الساعات, MARAHEL/DOWN=أعلام,
 *  ElectricOff=خلل الحساس, wiresActive=حالة الأسلاك.
 */
#include <WiFiS3.h>

const char* WIFI_SSID  = "اسم_الشبكة";
const char* WIFI_PASS  = "كلمة_مرور_الشبكة";
const char* SERVER_HOST = "192.168.1.20";
const int   SERVER_PORT = 8000;
const char* DEVICE_KEY  = "dvk_ضع_مفتاحك_هنا";

WiFiClient client;

void setup() {
  Serial.begin(115200);
  WiFi.begin(WIFI_SSID, WIFI_PASS);
  while (WiFi.status() != WL_CONNECTED) { delay(500); Serial.print("."); }
  Serial.println("\nمتصل بالواي فاي");
}

void sendReading(float c1, float i1, float x, int H, int electricOff, const char* wires) {
  if (!client.connect(SERVER_HOST, SERVER_PORT)) { Serial.println("فشل الاتصال"); return; }

  String body = String("{")
    + "\"c1\":" + c1 + ","
    + "\"i1\":" + i1 + ","
    + "\"x\":"  + x  + ","
    + "\"H\":"  + H  + ","
    + "\"ElectricOff\":" + electricOff + ","
    + "\"wiresActive\":\"" + wires + "\""
    + "}";

  client.println("POST /device/readings HTTP/1.1");
  client.print("Host: "); client.println(SERVER_HOST);
  client.print("X-Device-Key: "); client.println(DEVICE_KEY);
  client.println("Content-Type: application/json");
  client.print("Content-Length: "); client.println(body.length());
  client.println("Connection: close");
  client.println();
  client.println(body);

  while (client.connected() || client.available()) {
    if (client.available()) Serial.write(client.read());
  }
  client.stop();
  Serial.println("\nأُرسلت القراءة");
}

void loop() {
  float c1 = readThermocouple();   // الحرارة الحقيقية من الحساس
  float i1 = 850.0;                // الافتراضية (من منطق برنامجك)
  float x  = 1000.0;              // الدرجة النهائية
  int   H  = 2;                   // حالة البرنامج
  sendReading(c1, i1, x, H, 0, "تضخ");
  delay(10000);                   // كل 10 ثوانٍ
}

float readThermocouple() {
  return 845.5;  // مؤقت — استبدله بقراءة MAX31855 الفعلية
}

/*
 * ═══════════════════════════════════════════════════════════
 *  إضافة: سؤال الخادم عن أمر الإيقاف الإجباري
 * ═══════════════════════════════════════════════════════════
 *  استدعِ checkStop() دورياً (مثلاً بعد كل إرسال قراءة).
 *  لو رجّع true، نفّذ إيقاف برنامج الحرق عندك.
 */
bool checkStop() {
  if (!client.connect(SERVER_HOST, SERVER_PORT)) return false;
  client.println("GET /device/stop-status HTTP/1.1");
  client.print("Host: "); client.println(SERVER_HOST);
  client.print("X-Device-Key: "); client.println(DEVICE_KEY);
  client.println("Connection: close");
  client.println();

  String response = "";
  while (client.connected() || client.available()) {
    if (client.available()) response += (char)client.read();
  }
  client.stop();
  // لو احتوى الرد على "true" فهناك أمر إيقاف
  return response.indexOf("\"stop_requested\":true") >= 0;
}
