#include <Arduino.h>
#include <esp_arduino_version.h>
#include <math.h>

// ============================================================
// ARGUS ESP32 Active Warning Controller - Public Prototype
// 支持协议：
//   @T,seq,valid,xn,yn,danger,alarm                 旧归一化坐标协议（0~1000）
//   T,seq,zone_id,cx,cy,img_w,img_h,score,light,beep 兼容普通T坐标协议
//   A,seq,zone_id,pan,tilt,score,light,beep          新角度协议
//   C                                                回中
//   L,seq                                            丢失/停止报警
//
// 目标：配合 bisai4 动态风险主动干预系统，提高舵机稳定性、降低抖动、减少误报蜂鸣。
// ============================================================


// =======================
// ESP32E 引脚
// 按你当前已验证可运行的接线保留
// =======================
const int PAN_PIN = 25;       // 水平舵机
const int TILT_PIN = 26;      // 俯仰舵机
const int BUZZER_PIN = 27;    // 蜂鸣器

const int PAN_CH = 0;
const int TILT_CH = 1;


// =======================
// 蜂鸣器
// 如果蜂鸣器没发指令就响，把 true 改 false
// 如果发报警不响，也改这里
// =======================
const bool BUZZER_ACTIVE_LOW = true;


// =======================
// 舵机角度与方向
// =======================
float panDeg = 90.0f;
float tiltDeg = 90.0f;

float panTargetDeg = 90.0f;
float tiltTargetDeg = 90.0f;

const float PAN_CENTER = 90.0f;
const float TILT_CENTER = 90.0f;

const float PAN_MIN = 20.0f;
const float PAN_MAX = 160.0f;
const float TILT_MIN = 30.0f;
const float TILT_MAX = 150.0f;

// 方向反了改这里
const int PAN_DIR = -1;
const int TILT_DIR = 1;


// =======================
// 坐标 -> 角度映射
// 比旧版线性映射更稳：
// - 中心附近更细腻，不容易抖
// - 偏差大时仍有足够转向范围
// =======================
const float PAN_MAX_OFFSET_DEG = 48.0f;   // xn 从中心到边缘时最大水平偏移
const float TILT_MAX_OFFSET_DEG = 42.0f;  // yn 从中心到边缘时最大俯仰偏移
const float EXPO_POWER = 1.25f;           // >1: 中心更柔和，边缘更明显

// 双阈值死区：进入中心锁定后，必须偏得更远才释放，避免边界来回抖
const int CENTER_LOCK_DEADBAND = 25;
const int CENTER_RELEASE_DEADBAND = 45;
bool centerLockX = false;
bool centerLockY = false;

// 目标角度变化小于这个值时不更新，减少PWM小抖动
const float TARGET_UPDATE_EPS_DEG = 0.35f;

// 目标角度EMA，越大响应越快，越小越稳
const float TARGET_EMA_ALPHA = 0.55f;


// =======================
// 坐标滤波：中值滤波 + 自适应EMA
// =======================
const int MEDIAN_N = 5;
int xHist[MEDIAN_N] = {500, 500, 500, 500, 500};
int yHist[MEDIAN_N] = {500, 500, 500, 500, 500};
int histIdx = 0;
int histCount = 0;

float filtXn = 500.0f;
float filtYn = 500.0f;
bool filterReady = false;


// =======================
// 舵机平滑运动
// 自适应步进：距离远时快，接近目标时慢
// =======================
const unsigned long SERVO_UPDATE_INTERVAL_MS = 20;
const float SERVO_MIN_STEP_DEG = 0.35f;
const float SERVO_MAX_STEP_DEG = 3.2f;
const float SERVO_STEP_GAIN = 0.24f;
const float SERVO_SETTLE_EPS_DEG = 0.18f;


// =======================
// 超时与报警确认
// =======================
const unsigned long LOST_TIMEOUT_MS = 1500;      // 多久没收到目标就认为丢失
const unsigned long ALARM_CONFIRM_MS = 120;      // 风险持续超过该时间才蜂鸣，防止单帧误报
const unsigned long SERIAL_HEARTBEAT_MS = 2000;  // 状态心跳打印间隔


// =======================
// 状态
// =======================
String lineBuf = "";

unsigned long lastTargetMs = 0;
unsigned long lastServoUpdateMs = 0;
unsigned long lastAlarmToggleMs = 0;
unsigned long alarmCandidateStartMs = 0;
unsigned long lastHeartbeatMs = 0;

int desiredAlarmLevel = 0;   // RDK当前要求的报警等级
int alarmLevel = 0;          // 实际执行的报警等级，经过确认延迟
bool buzzerState = false;
bool hasTarget = false;
bool directAngleMode = false;  // A协议直接角度模式

long lastSeq = 0;


// =======================
// 小工具
// =======================
float clampFloat(float v, float lo, float hi) {
  if (v < lo) return lo;
  if (v > hi) return hi;
  return v;
}

int clampInt(int v, int lo, int hi) {
  if (v < lo) return lo;
  if (v > hi) return hi;
  return v;
}

int signInt(float x) {
  if (x > 0) return 1;
  if (x < 0) return -1;
  return 0;
}

int splitCsv(const String &s, String parts[], int maxParts) {
  int count = 0;
  int start = 0;

  for (int i = 0; i <= s.length(); i++) {
    if (i == s.length() || s.charAt(i) == ',') {
      if (count < maxParts) {
        parts[count++] = s.substring(start, i);
      }
      start = i + 1;
    }
  }

  return count;
}


// =======================
// 蜂鸣器控制
// =======================
void buzzerWrite(bool on) {
  if (BUZZER_ACTIVE_LOW) {
    digitalWrite(BUZZER_PIN, on ? LOW : HIGH);
  } else {
    digitalWrite(BUZZER_PIN, on ? HIGH : LOW);
  }
}

void buzzerOff() {
  buzzerWrite(false);
  buzzerState = false;
}

void updateAlarmConfirm() {
  unsigned long now = millis();

  if (!hasTarget || desiredAlarmLevel <= 0) {
    alarmLevel = 0;
    alarmCandidateStartMs = 0;
    buzzerOff();
    return;
  }

  if (alarmCandidateStartMs == 0) {
    alarmCandidateStartMs = now;
  }

  if (now - alarmCandidateStartMs >= ALARM_CONFIRM_MS) {
    alarmLevel = clampInt(desiredAlarmLevel, 0, 3);
  } else {
    alarmLevel = 0;
  }
}

void handleAlarm() {
  updateAlarmConfirm();

  unsigned long now = millis();

  if (alarmLevel <= 0) {
    buzzerOff();
    return;
  }

  // 3级：持续响
  if (alarmLevel >= 3) {
    buzzerWrite(true);
    buzzerState = true;
    return;
  }

  // 1级慢响，2级快响
  unsigned long intervalMs = (alarmLevel == 1) ? 600 : 180;

  if (now - lastAlarmToggleMs >= intervalMs) {
    lastAlarmToggleMs = now;
    buzzerState = !buzzerState;
    buzzerWrite(buzzerState);
  }
}


// =======================
// PWM 舵机
// =======================
void servoAttachAll() {
#if ESP_ARDUINO_VERSION_MAJOR >= 3
  ledcAttach(PAN_PIN, 50, 16);
  ledcAttach(TILT_PIN, 50, 16);
#else
  ledcSetup(PAN_CH, 50, 16);
  ledcSetup(TILT_CH, 50, 16);
  ledcAttachPin(PAN_PIN, PAN_CH);
  ledcAttachPin(TILT_PIN, TILT_CH);
#endif
}

void writeServoPin(int pin, int ch, float angle) {
  angle = clampFloat(angle, 0.0f, 180.0f);

  int pulseUs = map((int)round(angle), 0, 180, 500, 2500);
  uint32_t duty = (uint32_t)(pulseUs * 65535UL / 20000UL);

#if ESP_ARDUINO_VERSION_MAJOR >= 3
  ledcWrite(pin, duty);
#else
  ledcWrite(ch, duty);
#endif
}

void writeServos() {
  writeServoPin(PAN_PIN, PAN_CH, panDeg);
  writeServoPin(TILT_PIN, TILT_CH, tiltDeg);
}

float adaptiveMoveToward(float current, float target) {
  float diff = target - current;
  float ad = fabs(diff);

  if (ad <= SERVO_SETTLE_EPS_DEG) {
    return target;
  }

  float step = clampFloat(ad * SERVO_STEP_GAIN, SERVO_MIN_STEP_DEG, SERVO_MAX_STEP_DEG);

  if (ad <= step) {
    return target;
  }

  return current + (diff > 0 ? step : -step);
}

void updateServosSmooth() {
  unsigned long now = millis();

  if (now - lastServoUpdateMs < SERVO_UPDATE_INTERVAL_MS) {
    return;
  }

  lastServoUpdateMs = now;

  panDeg = adaptiveMoveToward(panDeg, panTargetDeg);
  tiltDeg = adaptiveMoveToward(tiltDeg, tiltTargetDeg);

  panDeg = clampFloat(panDeg, PAN_MIN, PAN_MAX);
  tiltDeg = clampFloat(tiltDeg, TILT_MIN, TILT_MAX);

  writeServos();
}


// =======================
// 坐标滤波
// =======================
int medianSmall(int arr[], int n) {
  int tmp[MEDIAN_N];

  for (int i = 0; i < n; i++) {
    tmp[i] = arr[i];
  }

  for (int i = 0; i < n - 1; i++) {
    for (int j = i + 1; j < n; j++) {
      if (tmp[j] < tmp[i]) {
        int t = tmp[i];
        tmp[i] = tmp[j];
        tmp[j] = t;
      }
    }
  }

  return tmp[n / 2];
}

float adaptiveAlpha(float errAbs) {
  if (errAbs > 260.0f) return 0.52f;
  if (errAbs > 140.0f) return 0.40f;
  if (errAbs > 70.0f) return 0.30f;
  return 0.22f;
}

void pushCoordSample(int xn, int yn) {
  xn = clampInt(xn, 0, 1000);
  yn = clampInt(yn, 0, 1000);

  xHist[histIdx] = xn;
  yHist[histIdx] = yn;
  histIdx = (histIdx + 1) % MEDIAN_N;
  if (histCount < MEDIAN_N) histCount++;

  int mx = medianSmall(xHist, histCount);
  int my = medianSmall(yHist, histCount);

  if (!filterReady) {
    filtXn = mx;
    filtYn = my;
    filterReady = true;
    return;
  }

  float errAbs = fmaxf(fabs((float)mx - 500.0f), fabs((float)my - 500.0f));
  float a = adaptiveAlpha(errAbs);

  filtXn = a * mx + (1.0f - a) * filtXn;
  filtYn = a * my + (1.0f - a) * filtYn;
}


// =======================
// 坐标 -> 目标角度
// =======================
float expoOffsetFromError(float err, int dir, float maxOffsetDeg) {
  float absNorm = clampFloat(fabs(err) / 500.0f, 0.0f, 1.0f);
  float curved = pow(absNorm, EXPO_POWER);
  return (float)dir * (float)signInt(err) * curved * maxOffsetDeg;
}

void setTargetSmooth(float desiredPan, float desiredTilt) {
  desiredPan = clampFloat(desiredPan, PAN_MIN, PAN_MAX);
  desiredTilt = clampFloat(desiredTilt, TILT_MIN, TILT_MAX);

  if (fabs(desiredPan - panTargetDeg) > TARGET_UPDATE_EPS_DEG) {
    panTargetDeg = TARGET_EMA_ALPHA * desiredPan + (1.0f - TARGET_EMA_ALPHA) * panTargetDeg;
  }

  if (fabs(desiredTilt - tiltTargetDeg) > TARGET_UPDATE_EPS_DEG) {
    tiltTargetDeg = TARGET_EMA_ALPHA * desiredTilt + (1.0f - TARGET_EMA_ALPHA) * tiltTargetDeg;
  }

  panTargetDeg = clampFloat(panTargetDeg, PAN_MIN, PAN_MAX);
  tiltTargetDeg = clampFloat(tiltTargetDeg, TILT_MIN, TILT_MAX);
}

void setTargetFromCoord(int xn, int yn) {
  directAngleMode = false;

  pushCoordSample(xn, yn);

  float errX = filtXn - 500.0f;
  float errY = filtYn - 500.0f;

  float absX = fabs(errX);
  float absY = fabs(errY);

  // X轴死区滞回
  if (centerLockX) {
    if (absX > CENTER_RELEASE_DEADBAND) {
      centerLockX = false;
    }
  } else {
    if (absX <= CENTER_LOCK_DEADBAND) {
      centerLockX = true;
    }
  }

  // Y轴死区滞回
  if (centerLockY) {
    if (absY > CENTER_RELEASE_DEADBAND) {
      centerLockY = false;
    }
  } else {
    if (absY <= CENTER_LOCK_DEADBAND) {
      centerLockY = true;
    }
  }

  float desiredPan = panTargetDeg;
  float desiredTilt = tiltTargetDeg;

  if (!centerLockX) {
    desiredPan = PAN_CENTER + expoOffsetFromError(errX, PAN_DIR, PAN_MAX_OFFSET_DEG);
  }

  if (!centerLockY) {
    desiredTilt = TILT_CENTER + expoOffsetFromError(errY, TILT_DIR, TILT_MAX_OFFSET_DEG);
  }

  setTargetSmooth(desiredPan, desiredTilt);
}

void setTargetFromAngle(float pan, float tilt) {
  directAngleMode = true;
  centerLockX = false;
  centerLockY = false;
  setTargetSmooth(pan, tilt);
}

void centerServos() {
  hasTarget = false;
  desiredAlarmLevel = 0;
  alarmLevel = 0;
  alarmCandidateStartMs = 0;
  buzzerOff();

  centerLockX = false;
  centerLockY = false;
  directAngleMode = false;
  filterReady = false;
  histCount = 0;

  panTargetDeg = PAN_CENTER;
  tiltTargetDeg = TILT_CENTER;

  Serial.println("ACK:C center");
}

void lostTarget(long seq) {
  hasTarget = false;
  desiredAlarmLevel = 0;
  alarmLevel = 0;
  alarmCandidateStartMs = 0;
  buzzerOff();

  Serial.print("ACK:L seq=");
  Serial.println(seq);
}


// =======================
// 协议解析
// =======================
void parseATLine(const String &s) {
  // @T,seq,valid,xn,yn,danger,alarm
  String parts[8];
  int n = splitCsv(s, parts, 8);

  if (n < 7) {
    Serial.println("ERR @T bad packet");
    return;
  }

  long seq = parts[1].toInt();
  int valid = parts[2].toInt();
  int xn = clampInt(parts[3].toInt(), 0, 1000);
  int yn = clampInt(parts[4].toInt(), 0, 1000);
  int danger = parts[5].toInt();
  int alarm = clampInt(parts[6].toInt(), 0, 3);

  lastSeq = seq;
  lastTargetMs = millis();

  if (!valid) {
    lostTarget(seq);
    return;
  }

  hasTarget = true;
  desiredAlarmLevel = (danger > 0) ? alarm : 0;
  if (desiredAlarmLevel <= 0) {
    alarmCandidateStartMs = 0;
  }

  setTargetFromCoord(xn, yn);

  Serial.print("ACK:@T seq=");
  Serial.print(seq);
  Serial.print(" xn=");
  Serial.print(xn);
  Serial.print(" yn=");
  Serial.print(yn);
  Serial.print(" fx=");
  Serial.print(filtXn, 1);
  Serial.print(" fy=");
  Serial.print(filtYn, 1);
  Serial.print(" panNow=");
  Serial.print(panDeg, 1);
  Serial.print(" panTarget=");
  Serial.print(panTargetDeg, 1);
  Serial.print(" tiltNow=");
  Serial.print(tiltDeg, 1);
  Serial.print(" tiltTarget=");
  Serial.print(tiltTargetDeg, 1);
  Serial.print(" alarmCmd=");
  Serial.print(desiredAlarmLevel);
  Serial.print(" alarm=");
  Serial.print(alarmLevel);
  Serial.print(" lockX=");
  Serial.print(centerLockX ? 1 : 0);
  Serial.print(" lockY=");
  Serial.println(centerLockY ? 1 : 0);
}

void parseTLine(const String &s) {
  // T,seq,zone_id,cx,cy,img_w,img_h,score,light,beep
  String parts[12];
  int n = splitCsv(s, parts, 12);

  if (n < 10) {
    Serial.println("ERR T bad packet");
    return;
  }

  long seq = parts[1].toInt();
  int cx = parts[3].toInt();
  int cy = parts[4].toInt();
  int imgW = (int)max(1L, parts[5].toInt());
  int imgH = (int)max(1L, parts[6].toInt());
  int light = parts[8].toInt();
  int beep = clampInt(parts[9].toInt(), 0, 3);

  int xn = clampInt((int)round((float)cx * 1000.0f / (float)imgW), 0, 1000);
  int yn = clampInt((int)round((float)cy * 1000.0f / (float)imgH), 0, 1000);

  lastSeq = seq;
  lastTargetMs = millis();
  hasTarget = true;
  desiredAlarmLevel = (light > 0 || beep > 0) ? beep : 0;
  if (desiredAlarmLevel <= 0) {
    alarmCandidateStartMs = 0;
  }

  setTargetFromCoord(xn, yn);

  Serial.print("ACK:T seq=");
  Serial.print(seq);
  Serial.print(" xn=");
  Serial.print(xn);
  Serial.print(" yn=");
  Serial.print(yn);
  Serial.print(" panTarget=");
  Serial.print(panTargetDeg, 1);
  Serial.print(" tiltTarget=");
  Serial.print(tiltTargetDeg, 1);
  Serial.print(" alarmCmd=");
  Serial.println(desiredAlarmLevel);
}

void parseALine(const String &s) {
  // A,seq,zone_id,pan,tilt,score,light,beep
  String parts[10];
  int n = splitCsv(s, parts, 10);

  if (n < 8) {
    Serial.println("ERR A bad packet");
    return;
  }

  long seq = parts[1].toInt();
  int zoneId = parts[2].toInt();
  float pan = parts[3].toFloat();
  float tilt = parts[4].toFloat();
  int light = parts[6].toInt();
  int beep = clampInt(parts[7].toInt(), 0, 3);

  lastSeq = seq;
  lastTargetMs = millis();
  hasTarget = true;
  desiredAlarmLevel = (light > 0 || beep > 0) ? beep : 0;
  if (desiredAlarmLevel <= 0) {
    alarmCandidateStartMs = 0;
  }

  setTargetFromAngle(pan, tilt);

  Serial.print("ACK:A seq=");
  Serial.print(seq);
  Serial.print(" zone=");
  Serial.print(zoneId);
  Serial.print(" pan=");
  Serial.print(panTargetDeg, 1);
  Serial.print(" tilt=");
  Serial.print(tiltTargetDeg, 1);
  Serial.print(" alarmCmd=");
  Serial.println(desiredAlarmLevel);
}

void parseLine(String s) {
  s.trim();
  if (s.length() == 0) return;

  if (s == "C") {
    centerServos();
    return;
  }

  if (s.startsWith("L")) {
    String parts[3];
    int n = splitCsv(s, parts, 3);
    long seq = (n >= 2) ? parts[1].toInt() : 0;
    lostTarget(seq);
    return;
  }

  if (s.startsWith("@T,")) {
    parseATLine(s);
    return;
  }

  if (s.startsWith("T,")) {
    parseTLine(s);
    return;
  }

  if (s.startsWith("A,")) {
    parseALine(s);
    return;
  }

  Serial.print("ERR unknown protocol: ");
  Serial.println(s);
}


// =======================
// 初始化
// =======================
void setup() {
  Serial.begin(115200);
  delay(500);

  pinMode(BUZZER_PIN, OUTPUT);
  buzzerOff();

  servoAttachAll();

  panDeg = PAN_CENTER;
  tiltDeg = TILT_CENTER;
  panTargetDeg = PAN_CENTER;
  tiltTargetDeg = TILT_CENTER;

  writeServos();

  lastTargetMs = millis();

  Serial.println("READY:ARGUS ESP32 active warning controller");
  Serial.println("PAN=GPIO25 TILT=GPIO26 BUZZER=GPIO27");
  Serial.println("Protocols: @T, T, A, C, L");
  Serial.println("Stabilizer: median+adaptiveEMA+deadbandHysteresis+adaptiveServoStep+alarmConfirm");
}


// =======================
// 主循环
// =======================
void loop() {
  while (Serial.available()) {
    char c = Serial.read();

    if (c == '\n') {
      parseLine(lineBuf);
      lineBuf = "";
    } else if (c != '\r') {
      lineBuf += c;

      if (lineBuf.length() > 180) {
        lineBuf = "";
        Serial.println("ERR line too long");
      }
    }
  }

  if (millis() - lastTargetMs > LOST_TIMEOUT_MS) {
    if (hasTarget || desiredAlarmLevel > 0 || alarmLevel > 0) {
      Serial.println("ACK:TIMEOUT lost target, alarm off");
    }
    hasTarget = false;
    desiredAlarmLevel = 0;
    alarmLevel = 0;
    alarmCandidateStartMs = 0;
    buzzerOff();
  }

  updateServosSmooth();
  handleAlarm();

  unsigned long now = millis();
  if (now - lastHeartbeatMs >= SERIAL_HEARTBEAT_MS) {
    lastHeartbeatMs = now;
    Serial.print("HB pan=");
    Serial.print(panDeg, 1);
    Serial.print(" tilt=");
    Serial.print(tiltDeg, 1);
    Serial.print(" panT=");
    Serial.print(panTargetDeg, 1);
    Serial.print(" tiltT=");
    Serial.print(tiltTargetDeg, 1);
    Serial.print(" target=");
    Serial.print(hasTarget ? 1 : 0);
    Serial.print(" alarm=");
    Serial.print(alarmLevel);
    Serial.print(" mode=");
    Serial.println(directAngleMode ? "A" : "coord");
  }
}
