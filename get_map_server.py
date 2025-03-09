import requests
from PIL import Image
from io import BytesIO
import pyproj
from PIL import Image
from flask import Flask, request, send_file, make_response
from flask_cors import CORS

app = Flask(__name__)
CORS(app)  # Włącz CORS dla wszystkich routów


def convert_epsg_4326_to_2180(lat, lon):
    # Tworzymy obiekt dla układu EPSG:4326 (szerokość i długość geograficzna)
    wgs84 = pyproj.CRS("EPSG:4326")
    
    # Tworzymy obiekt dla układu EPSG:2180 (Polska)
    epsg_2180 = pyproj.CRS("EPSG:2180")
    
    # Inicjalizujemy transformację z EPSG:4326 na EPSG:2180
    transformer = pyproj.Transformer.from_crs(wgs84, epsg_2180, always_xy=True)
    
    # Przekształcamy współrzędne
    x, y = transformer.transform(lon, lat)
    
    return int(x), int(y)

def get_wms_bbox(address, delta = 20):

    try:
        # URL do wyszukiwania Nominatim
        nominatim_url = "https://nominatim.openstreetmap.org/search"

        # Parametry zapytania
        params = {
            "q": address,
            "format": "json",
            "limit": 1
        }

        # Nominatim wymaga ustawienia User-Agent
        headers = {"User-Agent": "Mozilla/5.0"}

        # Wykonanie zapytania
        response = requests.get(nominatim_url, params=params, headers=headers)
        data = response.json()
        data_bbox = data[0]["boundingbox"]    
        xmin, ymin = convert_epsg_4326_to_2180(float(data_bbox[0]), float(data_bbox[2]))
        xmax, ymax = convert_epsg_4326_to_2180(float(data_bbox[1]), float(data_bbox[3]))
        xmin -= delta
        ymin -= delta
        xmax += delta
        ymax += delta

        wms_bbox = f'{ymin},{xmin},{ymax},{xmax}'
        img_height = int(1000 * (ymax-ymin)/(xmax-xmin))

        return wms_bbox, img_height
    
    except Exception as e:
        raise RuntimeError(f"Geocoding error: {str(e)}")

def generate_map_image(address):
    try:
        wms_bbox, img_height = get_wms_bbox(address)

        # Parametry zapytania GetMap zgodne ze standardem WMS 1.3.0
        params = {
            "service": "WMS",
            "version": "1.3.0",
            "request": "GetMap",           # Określa, że chcemy pobrać mapę
            "layers": "",  # Dodaj nazwy warstw
            "styles": "",                  # Styl – pozostaw pusty, jeśli domyślny
            "crs": "EPSG:2180",            # Układ odniesienia – np. dla Polski często EPSG:2180
            "bbox": wms_bbox,  # Wartości bbox w formacie xmin,ymin,xmax,ymax
            "width": "1000",                # Szerokość obrazu w pikselach
            "height": str(img_height),               # Wysokość obrazu w pikselach
            "format": "image/png"          # Format obrazu
        }

        adr_url = "https://mapy.geoportal.gov.pl/wss/ext/KrajowaIntegracjaNumeracjiAdresowej"

        params["layers"] = "prg-ulice"

        # Pobranie mapy
        response = requests.get(adr_url, params=params)

        if response.status_code == 200:
            # Przekształcenie odpowiedzi do obrazu
            image_ulice = Image.open(BytesIO(response.content)).convert("RGBA")
        else:
            raise("Błąd zapytania WMS (ulice):", response.status_code)

        image_ogolny = image_ulice

        for x in range(image_ogolny.width):
            for y in range(image_ogolny.height):
                r, g, b, a = image_ogolny.getpixel((x, y))
                if a == 0:
                    image_ogolny.putpixel((x, y), (255, 255, 255, 255))

        params["layers"] = "budynki,dzialki,numery_dzialek,uzytki"
        # Adres serwera WMS OpenStreetMap (przykład)
        ewi_url = "https://integracja.gugik.gov.pl/cgi-bin/KrajowaIntegracjaEwidencjiGruntow"
        # Pobranie mapy
        response = requests.get(ewi_url, params=params)

        if response.status_code == 200:
            # Przekształcenie odpowiedzi do obrazu
            image_dzialki = Image.open(BytesIO(response.content)).convert("RGBA")
        else:
            raise("Błąd zapytania WMS (działki):", response.status_code)


        for y in range(image_dzialki.height):
            for x in range(image_dzialki.width):
                pixel_dzialki = image_dzialki.getpixel((x, y))

                # Sprawdzamy, czy piksel w image_dzialki nie jest biały
                if (pixel_dzialki[0] < 255 or pixel_dzialki[1] < 255 or pixel_dzialki[2] < 255) and pixel_dzialki[3] > 0:
                    ciemny_pixel = (int(pixel_dzialki[0] * 0.7), int(pixel_dzialki[1] * 0.7), int(pixel_dzialki[2] * 0.7))
                    # Jeśli piksel w image_dzialki jest nie-biały, kopiujemy go do image_ulice
                    image_ogolny.putpixel((x, y), ciemny_pixel)


        eko_layers = "GDOS:ObszaryChronionegoKrajobrazu,GDOS:ObszarySpecjalnejOchrony,GDOS:ParkiKrajobrazowe,GDOS:ParkiNarodowe,GDOS:PomnikiPrzyrody,GDOS:Rezerwaty,GDOS:SpecjalneObszaryOchrony,GDOS:StanowiskaDokumentacyjne,GDOS:UzytkiEkologiczne,GDOS:ZespolyPrzyrodniczoKrajobrazowe"
        params["layers"] = eko_layers
        eko_wms_url = "https://sdi.gdos.gov.pl/wms"

        response = requests.get(eko_wms_url, params=params)

        # Sprawdzenie, czy zapytanie się powiodło
        if response.status_code == 200:
            # Odczyt obrazu z odpowiedzi
            image_eko = Image.open(BytesIO(response.content)).convert("RGBA")
            # Przeszukiwanie pikseli
            for x in range(image_eko.width):
                for y in range(image_eko.height):
                    r, g, b, a = image_eko.getpixel((x, y))
                    if (r, g, b) != (255, 255, 255):  # Sprawdzenie, czy piksel nie jest biały
                        image_eko.putpixel((x, y), (124, 252, 0, int(0.4*255)))
                    else:
                        image_eko.putpixel((x, y), (255, 255, 255, 0))     
        else:
            raise("Błąd zapytania WMS (ekologia):", response.status_code)

        image_ogolny = Image.alpha_composite(image_ogolny, image_eko)

        zabytki_wms_url = "https://usluga.zabytek.gov.pl/INSPIRE_IMD/service.svc/get"

        params["layers"] = "Immovable_Monuments"

        # Wykonanie zapytania GET do usługi WMS
        response = requests.get(zabytki_wms_url, params=params)

        # Sprawdzenie, czy zapytanie się powiodło
        if response.status_code == 200:
            # Odczyt obrazu z odpowiedzi
            image_zabytki = Image.open(BytesIO(response.content)).convert("RGBA")
            # Przeszukiwanie pikseli
            for x in range(image_zabytki.width):
                for y in range(image_zabytki.height):
                    r, g, b, a = image_zabytki.getpixel((x, y))
                    if (r, g, b) != (255, 255, 255):  # Sprawdzenie, czy piksel nie jest biały
                        image_zabytki.putpixel((x, y), (220, 30, 30, int(0.5*255)))
                    else:
                        image_zabytki.putpixel((x, y), (255, 255, 255, 0))
        else:
            raise("Błąd zapytania WMS (zabytki):", response.status_code)

        image_ogolny = Image.alpha_composite(image_ogolny, image_zabytki)
       
        # Przygotuj wynikowy obraz
        output = BytesIO()
        image_ogolny.save(output, format='PNG')
        output.seek(0)
        
        return output
    
    except Exception as e:
        raise RuntimeError(f"Map generation error: {str(e)}")
     

@app.route('/generate-map', methods=['POST'])
def handle_request():
    address = request.form.get('address')
    
    if not address:
        return make_response("Missing address parameter", 400)
    
    try:
        image_data = generate_map_image(address)
        return send_file(image_data, mimetype='image/png')
    
    except Exception as e:
        return make_response(str(e), 500)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
