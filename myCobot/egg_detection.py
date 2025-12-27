import cv2
import socket
import time
import threading
import numpy as np
from ultralytics import YOLO

# ==========================================
# 1. 티칭 데이터셋 (유저 데이터)
# ==========================================
P1_HOME   = [216.4, 115.6, 213.5, -179.46, -0.16, 41.39]
P2_PICK   = [206.7, 133.4, 43.2, 176.73, -8.66, 23.42]
P3_PLACE  = [210.7, 119.4, 34.6, 175.46, -15.0, 27.87]
P5_RESET  = [98.5, 31.4, 218.1, 163.03, -23.78, 42.81]

GOLDEN_R_POS = [P2_PICK[0], P2_PICK[1], 220.0, P2_PICK[3], P2_PICK[4], P2_PICK[5]]

ROBOT_IP = "172.20.10.5"
MODEL_PATH = r"C:/Users/solin/OneDrive/바탕 화면/best_egg.pt"

# 제어 변수 (안정적인 조준을 위해 K값 보수적 설정)
K = 0.36
GOLDEN_P_POS = [320, 240]

# ==========================================
# 2. 카메라 스레드 (최신 프레임 획득)
# ==========================================
class FreshFrame(threading.Thread):
    def __init__(self, url):
        super().__init__()
        self.url = url
        self.cap = cv2.VideoCapture(url, cv2.CAP_FFMPEG)
        self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        self.frame = None
        self.stopped = False

    def run(self):
        while not self.stopped:
            try:
                ret, frame = self.cap.read()
                if ret: self.frame = frame
                else:
                    self.cap.release()
                    time.sleep(1)
                    self.cap = cv2.VideoCapture(self.url, cv2.CAP_FFMPEG)
            except: time.sleep(0.5)

    def stop(self):
        self.stopped = True
        if self.cap: self.cap.release()

# ==========================================
# 3. 초기화 및 통신
# ==========================================
model = YOLO(MODEL_PATH)
client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
client_socket.connect((ROBOT_IP, 9000))

def send_robot(pos, speed, grip):
    # 속도를 인자로 받지만, 안전을 위해 내부에서 제한할 수도 있습니다.
    msg = f"{pos[0]:.1f},{pos[1]:.1f},{pos[2]:.1f},{pos[3]:.1f},{pos[4]:.1f},{pos[5]:.1f},{speed},{grip}"
    client_socket.sendall(msg.encode('utf-8'))

# 상태 정의
STATE_INIT_HOME  = "INIT_HOME"
STATE_CALIB_P1   = "CALIB_P1"
STATE_CALIB_WAIT = "CALIB_WAIT"
STATE_CALIB_P2   = "CALIB_P2"
STATE_ALIGN      = "ALIGNING"
STATE_PICK       = "PICKING"
STATE_PLACE      = "PLACING"
STATE_RESET      = "RESET"

current_state = STATE_INIT_HOME
stream = FreshFrame(f"http://{ROBOT_IP}:8080/?action=stream")
stream.start()

calib_start_p = None
calib_wait_start = 0
align_start_time = 0
target_x, target_y = GOLDEN_R_POS[0], GOLDEN_R_POS[1]

print("🐢 [Tempo Control] 저속 정밀 모드로 시작합니다.")

while True:
    frame = stream.frame
    if frame is None: continue

    results = model.predict(frame, conf=0.5, verbose=False, imgsz=320)
    egg = None
    for r in results:
        for box in r.boxes:
            b = box.xyxy[0].cpu().numpy()
            egg = (int((b[0]+b[2])/2), int((b[1]+b[3])/2))
            cv2.rectangle(frame, (int(b[0]), int(b[1])), (int(b[2]), int(b[3])), (0, 255, 0), 2)
            break

    # --- 상태 머신 (템포 조절 버전) ---

    # [1] 홈 이동 (속도 낮춤: 40 -> 20)
    if current_state == STATE_INIT_HOME:
        print("🏠 [1/6] 홈 이동 (저속)...")
        send_robot(P1_HOME, 20, 1) 
        time.sleep(5.0) # 충분히 대기
        current_state = STATE_CALIB_P1

    # [2-1] 캘리브레이션 P1 (속도 낮춤: 30 -> 15)
    elif current_state == STATE_CALIB_P1:
        if egg:
            print("🛠️ [2/6] 기준점 이동 및 P1 측정")
            send_robot(GOLDEN_R_POS, 15, 1); time.sleep(4.0)
            calib_start_p = egg
            test_pos = GOLDEN_R_POS.copy(); test_pos[1] += 30.0
            send_robot(test_pos, 10, 1) # 아주 천천히 이동
            calib_wait_start = time.time()
            current_state = STATE_CALIB_WAIT

    # [2-2] 이동 대기 (대기 시간 증가)
    elif current_state == STATE_CALIB_WAIT:
        if time.time() - calib_wait_start > 4.5: # 4.5초간 영상 안정화 대기
            current_state = STATE_CALIB_P2

    # [2-3] K값 도출
    elif current_state == STATE_CALIB_P2:
        if egg:
            dist_px = np.sqrt((egg[0]-calib_start_p[0])**2 + (egg[1]-calib_start_p[1])**2)
            if dist_px > 5:
                K = 30.0 / dist_px
                GOLDEN_P_POS = list(calib_start_p)
                print(f"✅ K값 도출: {K:.4f}")
                align_start_time = time.time()
                current_state = STATE_ALIGN
            else: 
                print("❌ 이동량 부족, 다시 시도")
                current_state = STATE_INIT_HOME

    # [3] 정밀 조준 (가장 속도가 중요한 구간)
    elif current_state == STATE_ALIGN:
        if egg:
            diff_px = egg[0] - GOLDEN_P_POS[0]
            diff_py = egg[1] - GOLDEN_P_POS[1]
            
            # 이동량을 더 보수적으로 (K의 0.6배만 이동)
            target_x = GOLDEN_R_POS[0] + (diff_py * K * 0.6)
            target_y = GOLDEN_R_POS[1] + (diff_px * K * 0.6)
            
            # 안전 범위 제한
            target_x = max(140, min(220, target_x))
            target_y = max(-100, min(100, target_y))
            
            align_pos = [target_x, target_y, 220.0, GOLDEN_R_POS[3], GOLDEN_R_POS[4], GOLDEN_R_POS[5]]
            send_robot(align_pos, 10, 1) # 속도 10으로 아주 신중하게 이동
            
            elapsed = time.time() - align_start_time
            print(f"🎯 [3/6] 조준 중 (저속).. 오차X:{diff_px} | 경과:{elapsed:.1f}s")

            if (abs(diff_px) < 15 and abs(diff_py) < 15) or (elapsed > 8.0):
                print("✨ 조준 완료/타임아웃! 2초간 정지 후 집기 진입")
                time.sleep(2.0) # 집기 전 마지막 안정화
                current_state = STATE_PICK
            else:
                time.sleep(2.5) # 이동 후 영상이 따라올 때까지 '확실히' 대기

    # [4] 집기 (템포 늦춤)
    elif current_state == STATE_PICK:
        print("📥 [4/6] 집기 시퀀스")
        send_robot(align_pos, 10, 0); time.sleep(2.0) # 미리 열기
        pick_pos = [target_x, target_y, P2_PICK[2], P2_PICK[3], P2_PICK[4], P2_PICK[5]]
        send_robot(pick_pos, 8, 0); time.sleep(4.0) # 아주 천천히 하강
        send_robot(pick_pos, 10, 1); time.sleep(3.0) # 꽉 집기
        pick_pos[2] = 220.0; send_robot(pick_pos, 15, 1); time.sleep(2.5) # 상승
        current_state = STATE_PLACE

    # [5] 놓기 (안전 속도)
    elif current_state == STATE_PLACE:
        print("🚚 [5/6] 놓기 이동 (P3)")
        send_robot(P3_PLACE, 15, 1); time.sleep(5.0)
        send_robot(P3_PLACE, 10, 0); time.sleep(2.0) # 열기
        current_state = STATE_RESET

    # [6] 복귀
    elif current_state == STATE_RESET:
        print("✨ [6/6] 최종 복귀 (P5)")
        send_robot(P5_RESET, 20, 1); time.sleep(4.0)
        break

    cv2.imshow("Slow & Stable Egg System", frame)
    if cv2.waitKey(1) & 0xFF == ord('q'): break

stream.stop()
cv2.destroyAllWindows()