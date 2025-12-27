import sys
import termios
import tty
from pymycobot.myagv import MyAgv

# 이미지 설정값 참고
PORT = "/dev/ttyAMA2"
BAUD = 115200
agv = MyAgv(PORT, BAUD)

# 키보드 입력을 읽어오는 함수 (설치 불필요)
def get_key():
    fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd)
    try:
        tty.setraw(sys.stdin.fileno())
        ch = sys.stdin.read(1)
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
    return ch

print("=== myAGV 오프라인 키보드 제어 ===")
print("w: 전진 / s: 후진 / a: 좌이동 / d: 우이동")
print("q: 좌회전 / e: 우회전 / space: 정지 / x: 종료")

try:
    while True:
        key = get_key()
        
        if key == 'w':
            agv.go_ahead(50, timeout=0.5)
        elif key == 's':
            agv.retreat(50, timeout=0.5)
        elif key == 'a':
            agv.pan_left(50, timeout=0.5)
        elif key == 'd':
            agv.pan_right(50, timeout=0.5)
        elif key == 'q':
            agv.counterclockwise_rotation(50, timeout=0.5)
        elif key == 'e':
            agv.clockwise_rotation(50, timeout=0.5)
        elif key == ' ':
            agv.stop()
        elif key == 'x':
            agv.stop()
            break
except Exception as e:
    print(e)
finally:
    agv.stop()