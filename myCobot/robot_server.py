import socket
import time
from pymycobot import MyCobot280

# 포트와 보드레이트 재확인 (get_angles가 -1 나오면 115200으로도 테스트)
mc = MyCobot280("/dev/ttyAMA0", 1000000)

def start_server():
    host = "0.0.0.0"
    port = 9000
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1) # 포트 재사용
    server_socket.bind((host, port))
    server_socket.listen(1)
    
    print("🤖 MyCobot 서버 대기 중...")

    while True:
        conn, addr = server_socket.accept()
        print(f"✅ 연결됨: {addr}")
        
        try:
            while True:
                # 데이터 수신 및 유효성 검사
                raw_data = conn.recv(1024).decode('utf-8')
                if not raw_data: break
                
                # [개선] 패킷이 뭉쳐서 올 경우를 대비해 마지막 명령만 수행하거나 분리
                commands = raw_data.strip().split('\n')
                last_command = commands[-1] 
                
                try:
                    val = list(map(float, last_command.split(',')))
                    if len(val) < 8: continue
                    
                    coords = val[:6]
                    speed = int(val[6])
                    grip = int(val[7])

                    # 1. 로봇 이동 (좌표가 유효한지 get_coords로 먼저 비교해보는 것이 좋음)
                    print(f"📥 이동: {coords} | 속도: {speed}")
                    mc.send_coords(coords, speed, 1) # 1: 선형이동
                    
                    # 2. 그리퍼 (그리퍼 모드 설정을 선행하면 더 안정적임)
                    # mc.set_gripper_mode(0) 
                    if grip == 1:
                        mc.set_gripper_state(1, 70) 
                    else:
                        mc.set_gripper_state(0, 70)

                    # [중요] 로봇이 처리할 물리적 시간을 줌 (명령 폭주 방지)
                    time.sleep(0.05) 

                except ValueError:
                    print("⚠️ 데이터 형식 오류 (Skip)")
                    continue
                    
        except Exception as e:
            print(f"❌ 세션 오류: {e}")
        finally:
            conn.close()

if __name__ == "__main__":
    # 시작 전 통신 체크
    res = mc.get_angles()
    if res == -1 or not res:
        print("🚨 경고: 로봇과 시리얼 통신이 연결되지 않았습니다! (결과: -1)")
    else:
        print(f"✅ 로봇 연결 확인. 현재 각도: {res}")
        mc.resume()
        start_server()