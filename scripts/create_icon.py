"""Render a metallic NEXVARY USB smartcard logo without bundled font files."""
from pathlib import Path
from PIL import Image, ImageDraw

OUT=Path("assets")
OUT.mkdir(exist_ok=True)
img=Image.new("RGBA",(512,512),(0,0,0,0))
d=ImageDraw.Draw(img)
d.rounded_rectangle((12,12,499,499),radius=110,fill="#081621",outline="#648EA7",width=12)
d.rounded_rectangle((36,36,474,474),radius=94,outline="#233A52",width=7)
d.polygon([(255,90),(392,153),(377,323),(255,421),(132,323),(118,153)],fill="#153B50")
d.line([(255,90),(392,153),(377,323),(255,421),(132,323),(118,153),(255,90)],fill="#57DCEB",width=17,joint="curve")
d.rounded_rectangle((201,181,321,318),radius=16,fill="#EFC66C",outline="#FAE6A8",width=7)
d.polygon([(278,182),(322,226),(322,187)],fill="#80602D")
for y in (222,263):
    d.line((216,y,307,y),fill="#8F6E34",width=6)
d.line((252,189,252,309),fill="#8F6E34",width=5)
d.rounded_rectangle((231,124,282,178),radius=5,fill="#E5F9FE")
d.rectangle((240,131,251,142),fill="#12526B")
d.rectangle((262,131,273,142),fill="#12526B")
d.line([(255,322),(255,358)],fill="#F4C569",width=14)
d.ellipse((247,354,265,372),fill="#F4C569")
img.save(OUT/"nexvary-usb.ico",format="ICO",sizes=[(16,16),(24,24),(32,32),(48,48),(64,64),(128,128),(256,256)])
img.save(OUT/"nexvary-usb.png")
print(OUT/"nexvary-usb.ico")
# Installer wizard artwork generated from the original NEXVARY emblem.
from PIL import ImageFont
try:font=ImageFont.truetype('segoeuib.ttf',19)
except OSError:font=ImageFont.load_default()
large=Image.new('RGB',(164,314),'#0C1319')
large.paste(img.resize((132,132)),(16,38),img.resize((132,132)))
ld=ImageDraw.Draw(large);ld.text((19,191),'NEXVARY',font=font,fill='#B5BEC6')
ld.text((21,231),'USB STUDIO',fill='#6A9BD0');ld.line((19,267,145,267),fill='#E7BE69',width=3)
large.save(OUT/'wizard-large.bmp')
small=Image.new('RGB',(55,55),'#0C1319');small.paste(img.resize((49,49)),(3,3),img.resize((49,49)));small.save(OUT/'wizard-small.bmp')
