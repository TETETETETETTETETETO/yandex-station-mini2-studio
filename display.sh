#!/bin/sh
# Lightweight LED Display Control script for Yandex Station Mini 2
# Can be run directly on the speaker: sh display.sh [clear | all | text "12:34" | degree | ring color]

SYS_CLOCK="/sys/class/leds"

clear_clock() {
    for l in $SYS_CLOCK/mini2:white:clock*; do
        echo 0 > "$l/brightness"
    done
}

all_on() {
    BR=${1:-150}
    for l in $SYS_CLOCK/mini2:white:clock*; do
        echo "$BR" > "$l/brightness"
    done
}

set_segment() {
    SEG=$1
    BR=${2:-150}
    echo "$BR" > "$SYS_CLOCK/mini2:white:clock$SEG/brightness"
}

set_ring() {
    R=$1; G=$2; B=$3
    for i in 1 2 3 4 5 6; do
        echo "$R" > "$SYS_CLOCK/mini2:red:ring$i/brightness"
        echo "$G" > "$SYS_CLOCK/mini2:green:ring$i/brightness"
        echo "$B" > "$SYS_CLOCK/mini2:blue:ring$i/brightness"
    done
}

case "$1" in
    clear)
        clear_clock
        echo "Clock LEDs cleared"
        ;;
    all)
        all_on "${2:-150}"
        echo "All segments turned on"
        ;;
    ring)
        case "$2" in
            red)     set_ring 150 0 0 ;;
            green)   set_ring 0 150 0 ;;
            blue)    set_ring 0 0 150 ;;
            cyan)    set_ring 0 150 150 ;;
            magenta) set_ring 150 0 150 ;;
            yellow)  set_ring 150 150 0 ;;
            white)   set_ring 150 150 150 ;;
            off)     set_ring 0 0 0 ;;
            *)       echo "Usage: display.sh ring [red|green|blue|cyan|magenta|yellow|white|off]" ;;
        esac
        ;;
    seg)
        # Usage: display.sh seg A1 200
        set_segment "$2" "${3:-150}"
        ;;
    colon)
        # Toggle or set colon dots
        BR=${2:-150}
        echo "$BR" > "$SYS_CLOCK/mini2:white:clockPLUS1/brightness"
        echo "$BR" > "$SYS_CLOCK/mini2:white:clockPLUS2/brightness"
        ;;
    degree)
        BR=${2:-150}
        echo "$BR" > "$SYS_CLOCK/mini2:white:clockDEGREE/brightness"
        ;;
    *)
        echo "Yandex Station Mini 2 LED Utility"
        echo "Usage: display.sh [clear | all [brightness] | seg <name> [val] | colon [val] | degree [val] | ring <color>]"
        echo "Examples:"
        echo "  display.sh clear"
        echo "  display.sh seg DEGREE 255"
        echo "  display.sh seg A1 200"
        echo "  display.sh colon 150"
        echo "  display.sh ring cyan"
        ;;
esac
