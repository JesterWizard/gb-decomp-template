; Tiny synthetic CGB-compatible MBC1 ROM used to smoke-test the template.
; Not a real game. Built with: rgbasm + rgblink + rgbfix (see test/Makefile)
INCLUDE "hardware.inc"

DEF wFrameCounter EQU $C000
DEF wScore EQU $C001
DEF hJoypad EQU $FF80

SECTION "rst0", ROM0[$00]
    ret
SECTION "vblank", ROM0[$40]
    jp VBlankHandler
SECTION "entry", ROM0[$100]
    nop
    jp Start
    ds $150 - @, 0

SECTION "main", ROM0[$150]
Start:
    di
    ld sp, $FFFE
    xor a
    ldh [rLCDC], a
    ld hl, $C000
    ld bc, $100
    call ClearMem
    ld a, 1
    ld [wScore], a
.loop:
    call AddScore
    ld a, 2
    ld [$2000], a          ; select bank 2
    call $4000             ; banked routine
    ld a, 1
    ld [$2000], a
    ld a, [wFrameCounter]
    inc a
    ld [wFrameCounter], a
    cp 10
    jr nz, .loop
    halt
    nop
    jr .loop

ClearMem:
    xor a
.l:
    ld [hl+], a
    dec bc
    ld a, b
    or c
    jr nz, .l
    ret

AddScore:
    ld a, [wScore]
    add a, 3
    ld [wScore], a
    ldh [hJoypad], a
    ret

VBlankHandler:
    push af
    ld a, [wFrameCounter]
    inc a
    ld [wFrameCounter], a
    pop af
    reti

PointerTable:
    dw Start, AddScore, ClearMem
Greeting:
    db "HELLO WORLD", 0

SECTION "bank1", ROMX[$4000], BANK[1]
Bank1Data:
    db $01, $02, $03, $04, $05, $06, $07, $08
    ds 16, $FF

SECTION "bank2", ROMX[$4000], BANK[2]
Bank2Routine:
    ld a, [wScore]
    add a, a
    ld [wScore], a
    call Bank2Helper
    ret
Bank2Helper:
    ld hl, $C000
    inc [hl]
    ret

SECTION "bank3", ROMX[$4000], BANK[3]
    ds 32, $AA
