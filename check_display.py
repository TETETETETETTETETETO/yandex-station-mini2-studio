import subprocess

adb = r"C:\Users\sguse\Desktop\platform-tools\adb.exe"
cmd = """
for i in 1 2 3 4; do
    printf "Digit %d: " $i
    for s in A B C D E F G; do
        b=$(cat /sys/class/leds/mini2:white:clock${s}${i}/brightness)
        if [ "$b" -gt 0 ]; then
            printf "%s " $s
        fi
    done
    printf "\n"
done
printf "PLUS1: %s\n" $(cat /sys/class/leds/mini2:white:clockPLUS1/brightness)
printf "PLUS2: %s\n" $(cat /sys/class/leds/mini2:white:clockPLUS2/brightness)
printf "DEGREE: %s\n" $(cat /sys/class/leds/mini2:white:clockDEGREE/brightness)
"""

res = subprocess.check_output([adb, "-s", "192.168.3.6:5555", "shell", cmd]).decode("utf-8")
print(res)
