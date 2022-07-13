#!/usr/bin/env python
"""
axis 0: left(-1), right(+1)
axis 1: up(-1), down(+1)
axis 2: L2 -1:1
axis 3: right stick left/right -1:1
axis 4: right stick up/down -1:1
axis 5: R2 -1:1
hats: (tuple) (L(-1)/R(1), UP(1)/DOWN(-1)) example (-1, -1)
buttons 
0: A
1: B
2: X
3: Y
4: L1
5: R1
6: select
7: start
8: HOME
9: LEFTSTICK BUTTON
10: RIGHTSTICK BUTTON


TODO: Joystick event handling should be better
      Maybe a function(s) inside joystick_handler()

      AxiDraw could have its own handler
      With all the low level commands and state bookkeeping

      Is it possible to check bounds through usb?
      Anyway it's important to check them

      Different modes to choose from? "Build a bezier" for example and an attractor
"""

import time
import os
import sys
from pyaxidraw import axidraw
import contextlib
with contextlib.redirect_stdout(None):
    import pygame

class joystick_handler():
    def __init__(self, id):
        self.id = id
        self.joy = pygame.joystick.Joystick(id)
        self.name = self.joy.get_name()
        self.joy.init()
        self.numaxes    = self.joy.get_numaxes()
        self.numballs   = self.joy.get_numballs()
        self.numbuttons = self.joy.get_numbuttons()
        self.numhats    = self.joy.get_numhats()

        self.axis = []
        for i in range(self.numaxes):
            self.axis.append(self.joy.get_axis(i))

        self.ball = []
        for i in range(self.numballs):
            self.ball.append(self.joy.get_ball(i))

        self.button = []
        for i in range(self.numbuttons):
            self.button.append(self.joy.get_button(i))

        self.hat = []
        for i in range(self.numhats):
            self.hat.append(self.joy.get_hat(i))

class axigame:
    JOYSTICK_NUMBER = 0
    DEADZONE = 0.10
    BOOST_MULTIPLIER = 5
    PEN_DOWN = False
    SLIDE_FACTOR = 0.95   # Float between .0-1 lower means less dampening
    FRICTION = 0.995
    MOVE_VECTOR = (0, 0)
    interval = 2         # Polling rate in milliseconds, 0 means practically whenever looping
    margin = 10          # Extra duration added to the command (interval+margin)
    scale = 30           # Multiplier for x,y direction, 1 means commands are 1-length steps
    time_old = time.time()*1000
    MAX_SPEED = scale*BOOST_MULTIPLIER

    def __init__(self):
        self.ad = axidraw.AxiDraw() # Initialize class
        self.ad.interactive()            # Enter interactive mode
        retry_counter = 0
        connected = False
        while (not connected and (retry_counter<10)):
            try:
                print("Connecting to AxiDraw")
                connected = self.ad.connect() # Try to open serial port to AxiDraw
            except:
                pass # Pass here because for some reason the first connection takes another try
            retry_counter += 1
        
        if not connected: sys.exit() 
        print("AxiDraw connected")

        # Enable motors, pen up
        self.ad.usb_command("EM,1,1\r")
        self.ad.usb_command("SP,1\r")
        print("Motors enabled")

        # Init pygame and create the joystick
        pygame.init()
        pygame.event.set_blocked(\
            (pygame.MOUSEMOTION, pygame.MOUSEBUTTONUP, pygame.MOUSEBUTTONDOWN))
        self.joy = joystick_handler(self.JOYSTICK_NUMBER)
        print("Controller:", self.joy.name)

        # Short rumble to indicate that everything is ready
        self.joy.joy.rumble(0, 1, 200)


    def run(self):
        while True:
            for event in pygame.event.get():
                if event.type == pygame.JOYAXISMOTION:
                    self.joy.axis[event.axis] = event.value
                elif event.type == pygame.JOYBALLMOTION:
                    self.joy.ball[event.ball] = event.rel
                elif event.type == pygame.JOYHATMOTION:
                    self.joy.hat[event.hat] = event.value
                elif event.type == pygame.JOYBUTTONUP:
                    self.joy.button[event.button] = 0
                elif event.type == pygame.JOYBUTTONDOWN:
                    self.joy.button[event.button] = 1

            # Commanding the AxiDraw at polling interval
            self.time_current = time.time()*1000
            if (self.time_current-self.time_old>=self.interval):
                if (self.joy.button[0]==1):
                    self.pen_down()
                else:
                    self.pen_up()

                # XBOX-button exits the loop immediately
                if(self.joy.button[6]==1 and self.joy.button[7]==1):
                    self.quit()

                # Run left stick operations and usb command
                self.left_stick()
                
                self.time_old=time.time()*1000

    def maprange(self, a, b, s):
        (a1, a2), (b1, b2) = a, b
        return  b1 + ((s - a1) * (b2 - b1) / (a2 - a1))

    def deadzone(self, input):
        output = input if abs(input)>self.DEADZONE else 0
        if (output < -self.DEADZONE):
            output = self.maprange((-1,-self.DEADZONE),(-1,0),output)
        elif (output > self.DEADZONE):
            output = self.maprange((self.DEADZONE,1),(0,1),output)
        return output
    
    def left_stick(self):
        global MOVE_VECTOR
        # JOYSTICK DEADZONE -(DEADZONE*int(axis[0]>0))
        axis_0 = self.deadzone(self.joy.axis[0])
        axis_1 = self.deadzone(self.joy.axis[1])

        # Boost speed with right trigger press
        speed_amount = self.scale*self.maprange((-1,1)\
            ,(1,self.BOOST_MULTIPLIER),self.joy.axis[5])

        # Slide factor with left trigger press
        slide_amount = self.maprange((-1, 1), (0, 1), self.joy.axis[2])

        # Move command variables
        duration = self.interval+self.margin
        a_0 = (axis_1*speed_amount)
        b_0 = (axis_0*-speed_amount)

        # Calculate final command with slide factor
        # move vector is orig command scaled down by slide amount
        # PLUS orig move vector scaled up by slide amount
        # so at 0: no orig move vector, full command
        # at 1: full orig move vector, no command
        # in the middle: some original move vector plus command

        # self.MOVE_VECTOR = (x*slide_amount for x in MOVE_VECTOR) # Scale
        orig_a, orig_b = self.MOVE_VECTOR
        self.MOVE_VECTOR = (a_0*(1-slide_amount*self.SLIDE_FACTOR)+orig_a*slide_amount\
            , b_0*(1-slide_amount*self.SLIDE_FACTOR)+orig_b*slide_amount)

        # LIMIT MAX SPEED
        a, b = (min(x, self.MAX_SPEED) if x>0 else max(x, -self.MAX_SPEED) for x in self.MOVE_VECTOR)
        self.MOVE_VECTOR = (a*self.FRICTION, b*self.FRICTION)

        # SEND COMMAND
        command = f"XM,{duration},{int(a)},{int(b)}\r"
        #print(command)
        self.ad.usb_command(command)

    def pen_down(self):
        if (not self.PEN_DOWN):
            self.ad.usb_command("SP,0\r")
            self.PEN_DOWN = True
        self.joy.joy.rumble(0, 0.1, 50)

    def pen_up(self):
        if (self.PEN_DOWN):
            self.ad.usb_command("SP,1\r")
            self.PEN_DOWN = False

    def quit(self):
        self.ad.usb_command("EM,0,0\r") # Disable motors
        print("Motors disabled")
        self.ad.disconnect()
        print("AxiDraw disconnected")
        pygame.quit()
        sys.exit()

if __name__ == "__main__":
    program = axigame()
    program.run()
