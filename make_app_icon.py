"""Render the app's own heart symbol for Windows shortcut and notification area."""
import math
from pathlib import Path
from PIL import Image,ImageDraw

def make_icon(root=Path(__file__).resolve().parent):
 assets=root/'assets';assets.mkdir(exist_ok=True)
 image=Image.new('RGBA',(256,256),(0,0,0,0));draw=ImageDraw.Draw(image)
 draw.rounded_rectangle((6,6,250,250),radius=58,fill='#276b54')
 points=[]
 for step in range(361):
  t=step*2*math.pi/360
  x=16*math.sin(t)**3;y=13*math.cos(t)-5*math.cos(2*t)-2*math.cos(3*t)-math.cos(4*t)
  points.append((128+x*5,122-y*5))
 draw.polygon(points,fill='white')
 draw.line([(68,127),(101,127),(117,100),(134,155),(150,124),(188,124)],fill='#276b54',width=10,joint='curve')
 image.save(assets/'app.png');image.save(assets/'app.ico',sizes=[(16,16),(24,24),(32,32),(48,48),(64,64),(128,128),(256,256)])

if __name__=='__main__':make_icon()
