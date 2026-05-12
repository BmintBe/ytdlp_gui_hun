from PIL import Image
img = Image.open('icon.png').resize((256,256), Image.LANCZOS).convert('RGBA')
img.save('icon.ico', format='ICO', sizes=[(16,16),(32,32),(48,48),(64,64),(128,128),(256,256)])
