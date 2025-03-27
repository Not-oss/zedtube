from PIL import Image, ImageDraw, ImageFont
import os

def create_default_thumbnail():
    # Créer une image de 640x360 pixels (format 16:9)
    width = 640
    height = 360
    image = Image.new('RGB', (width, height), color='#1a1a1a')
    draw = ImageDraw.Draw(image)
    
    # Ajouter un texte
    text = "ZedTube"
    try:
        # Essayer d'utiliser une police système
        font = ImageFont.truetype("arial.ttf", 60)
    except:
        # Si la police n'est pas trouvée, utiliser la police par défaut
        font = ImageFont.load_default()
    
    # Calculer la position du texte pour le centrer
    text_bbox = draw.textbbox((0, 0), text, font=font)
    text_width = text_bbox[2] - text_bbox[0]
    text_height = text_bbox[3] - text_bbox[1]
    x = (width - text_width) // 2
    y = (height - text_height) // 2
    
    # Dessiner le texte
    draw.text((x, y), text, font=font, fill='white')
    
    # Sauvegarder l'image
    if not os.path.exists('static'):
        os.makedirs('static')
    image.save('static/default_thumb.jpg', 'JPEG')

if __name__ == '__main__':
    create_default_thumbnail() 