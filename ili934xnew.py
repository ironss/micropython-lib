# This is an adapted version of the ILI934X driver as below.
# It works with multiple fonts and also works with the esp32 H/W SPI implementation
# Proportional fonts are generated by Peter Hinch's Font-to-py 
# MIT License; Copyright (c) 2017 Jeffrey N. Magee

# This file is part of MicroPython ILI934X driver
# Copyright (c) 2016 - 2017 Radomir Dopieralski, Mika Tuupola
# Copyright (c) 2019 Stephen Irons
#
# Licensed under the MIT license:
#   http://www.opensource.org/licenses/mit-license.php
#
# Project home:
#   https://github.com/tuupola/micropython-ili934x

import time
import ustruct
import glcdfont
import framebuf
from micropython import const

_RDDSDR = const(0x0f) # Read Display Self-Diagnostic Result
_SLPOUT = const(0x11) # Sleep Out
_GAMSET = const(0x26) # Gamma Set
_DISPOFF = const(0x28) # Display Off
_DISPON = const(0x29) # Display On
_CASET = const(0x2a) # Column Address Set
_PASET = const(0x2b) # Page Address Set
_RAMWR = const(0x2c) # Memory Write
_RAMRD = const(0x2e) # Memory Read
_MADCTL = const(0x36) # Memory Access Control
_VSCRSADD = const(0x37) # Vertical Scrolling Start Address
_PIXSET = const(0x3a) # Pixel Format Set
_PWCTRLA = const(0xcb) # Power Control A
_PWCRTLB = const(0xcf) # Power Control B
_DTCTRLA = const(0xe8) # Driver Timing Control A
_DTCTRLB = const(0xea) # Driver Timing Control B
_PWRONCTRL = const(0xed) # Power on Sequence Control
_PRCTRL = const(0xf7) # Pump Ratio Control
_PWCTRL1 = const(0xc0) # Power Control 1
_PWCTRL2 = const(0xc1) # Power Control 2
_VMCTRL1 = const(0xc5) # VCOM Control 1
_VMCTRL2 = const(0xc7) # VCOM Control 2
_FRMCTR1 = const(0xb1) # Frame Rate Control 1
_DISCTRL = const(0xb6) # Display Function Control
_ENA3G = const(0xf2) # Enable 3G
_PGAMCTRL = const(0xe0) # Positive Gamma Control
_NGAMCTRL = const(0xe1) # Negative Gamma Control

_CHUNK = const(1024) #maximum number of pixels per spi write


def color565(r, g=None, b=None):
    if not g and not b:
        color = r
        r = (color >> 16) & 0xFF
        g = (color >> 8) & 0xFF
        b = (color) & 0xFF
    return (r & 0xf8) << 8 | (g & 0xfc) << 3 | (b & 0xf8) >> 3

def colormap(fg_color, bg_color):
    fg = color565(fg_color)
    bg = color565(bg_color)
    _colormap = bytearray(b'\x00\x00\x00\x00')
    _colormap[0] = (bg >> 8) & 0xFF
    _colormap[1] = bg & 0xFF
    _colormap[2] = (fg >> 8) & 0xFF
    _colormap[3] = fg & 0xFF
    return _colormap
    

class ILI9341:
    def __init__(self, width, height, spi, cs, dc, rst):
        self.spi = spi
        self.width = width
        self.height = height
        self.cs = cs
        self.dc = dc
        self.rst = rst
        self.cs.init(self.cs.OUT, value=1)
        self.dc.init(self.dc.OUT, value=0)
        self.rst.init(self.rst.OUT, value=0)
        self.reset()
        self.init()
        self._buf = bytearray(_CHUNK * 2)
    
    def init(self):
        for command, data in (
            (_RDDSDR, b"\x03\x80\x02"),
            (_PWCRTLB, b"\x00\xc1\x30"),
            (_PWRONCTRL, b"\x64\x03\x12\x81"),
            (_DTCTRLA, b"\x85\x00\x78"),
            (_PWCTRLA, b"\x39\x2c\x00\x34\x02"),
            (_PRCTRL, b"\x20"),
            (_DTCTRLB, b"\x00\x00"),
            (_PWCTRL1, b"\x23"),
            (_PWCTRL2, b"\x10"),
            (_VMCTRL1, b"\x3e\x28"),
            (_VMCTRL2, b"\x86"),
            #(_MADCTL, b"\x48"),
            (_MADCTL, b"\x08"),
            (_PIXSET, b"\x55"),
            (_FRMCTR1, b"\x00\x18"),
            (_DISCTRL, b"\x08\x82\x27"),
            (_ENA3G, b"\x00"),
            (_GAMSET, b"\x01"),
            (_PGAMCTRL, b"\x0f\x31\x2b\x0c\x0e\x08\x4e\xf1\x37\x07\x10\x03\x0e\x09\x00"),
            (_NGAMCTRL, b"\x00\x0e\x14\x03\x11\x07\x31\xc1\x48\x08\x0f\x0c\x31\x36\x0f")):
            self._write(command, data)
        self._write(_SLPOUT)
        time.sleep_ms(120)
        self._write(_DISPON)

    def reset(self):
        self.rst(0)
        time.sleep_ms(50)
        self.rst(1)
        time.sleep_ms(50)

    def _write(self, command, data=None):
        self.dc(0)
        self.cs(0)
        self.spi.write(bytearray([command]))
        self.cs(1)
        if data is not None:
            self._data(data)

    def _data(self, data):
        self.dc(1)
        self.cs(0)
        self.spi.write(data)
        self.cs(1)

    def _writeblock(self, x0, y0, x1, y1, data=None):
        self._write(_CASET, ustruct.pack(">HH", x0, x1))
        self._write(_PASET, ustruct.pack(">HH", y0, y1))
        self._write(_RAMWR, data)

    def _readblock(self, x0, y0, x1, y1):
        self._write(_CASET, ustruct.pack(">HH", x0, x1))
        self._write(_PASET, ustruct.pack(">HH", y0, y1))
        if data is None:
            return self._read(_RAMRD, (x1 - x0 + 1) * (y1 - y0 + 1) * 3)

    def _read(self, command, count):
        self.dc(0)
        self.cs(0)
        self.spi.write(bytearray([command]))
        data = self.spi.read(count)
        self.cs(1)
        return data

    def pixel(self, x, y, color=None):
        if color is None:
            r, b, g = self._readblock(x, y, x, y)
            return color565(r, g, b)
        if not 0 <= x < self.width or not 0 <= y < self.height:
            return
        self._writeblock(x, y, x, y, ustruct.pack(">H", color565(color)))

    def fill_rect(self, x, y, w, h, color):
        x = min(self.width - 1, max(0, x))
        y = min(self.height - 1, max(0, y))
        w = min(self.width - x, max(1, w))
        h = min(self.height - y, max(1, h))
        color = ustruct.pack(">H", color565(color))
        for i in range(_CHUNK):
            self._buf[2*i]=color[0]; self._buf[2*i+1]=color[1]
        chunks, rest = divmod(w * h, _CHUNK)
        self._writeblock(x, y, x + w - 1, y + h - 1, None)
        if chunks:
            for count in range(chunks):
                self._data(self._buf)
        if rest != 0:
            mv = memoryview(self._buf)
            self._data(mv[:rest*2])

    def clear(self, color):
        self.fill_rectangle(0, 0, self.width, self.height, color)
    
    def circle(self, x, y, radius, fg_color=None, bg_color=None):
        self.fill_rectangle(x-radius, y-radius, radius*2, radius*2, fg_color)
        
    def blit(self, bitbuff, x, y, w, h, colormap):
        x = min(self.width - 1, max(0, x))
        y = min(self.height - 1, max(0, y))
        w = min(self.width - x, max(1, w))
        h = min(self.height - y, max(1, h))
        chunks, rest = divmod(w * h, _CHUNK)
        self._writeblock(x, y, x + w - 1, y + h - 1, None)
        written = 0
        for iy in range(h):
            for ix in range(w):
                index = ix+iy*w - written
                if index >=_CHUNK:
                    self._data(self._buf)
                    written += _CHUNK
                    index   -= _CHUNK
                c = bitbuff.pixel(ix,iy)
                self._buf[index*2] = colormap[c*2]
                self._buf[index*2+1] = colormap[c*2+1]
        rest = w*h - written
        if rest != 0:
            mv = memoryview(self._buf)
            self._data(mv[:rest*2])
    
    def line(self, x0, y, x1, y1, color=None):
        pass

    def text(self, text, x, y, font, fg, bg):
        text_w  = font.get_width(text)
        div, rem = divmod(font.height(),8)
        nbytes = div+1 if rem else div
        buf = bytearray(text_w * nbytes)
        pos = 0
        for ch in text:
            glyph, char_w = font.get_ch(ch)
            for row in range(nbytes):
                index = row*text_w + pos
                for i in range(char_w):
                    buf[index+i] = glyph[nbytes*i+row]
            pos += char_w
        fb = framebuf.FrameBuffer(buf, text_w, font.height(), framebuf.MONO_VLSB)
        self.blit(fb, x, y, text_w, font.height(), colormap(fg, bg) )
        return x + text_w

    def show(self):
        pass
