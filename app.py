import os
from dotenv import load_dotenv
from flask import Flask, request, render_template, redirect, session, url_for, send_file
from twilio.rest import Client
from twilio.base.exceptions import TwilioRestException
from twilio.twiml.messaging_response import Message, MessagingResponse
from werkzeug.utils import secure_filename
from werkzeug.datastructures import FileStorage
from image_classifier import get_tags
from flask_googlemaps import GoogleMaps, Map
import sqlite3
from sqlite3 import Error
from s3_functions import s3upload_file, get_presigned_url

load_dotenv()
GOOGLE_MAPS_API = os.environ.get('GOOGLE_MAPS_API')
TWILIO_ACCOUNT_SID = os.environ.get('TWILIO_ACCOUNT_SID')
TWILIO_AUTH_TOKEN= os.environ.get('TWILIO_AUTH_TOKEN')
VERIFY_SERVICE_SID= os.environ.get('VERIFY_SERVICE_SID')

app = Flask(__name__)
GoogleMaps(app, key=GOOGLE_MAPS_API)
UPLOAD_FOLDER = "uploads"
BUCKET = "lats-image-data"

app.secret_key = 'dsfdgfdg;sdyyuyy'
client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)

app.config['UPLOAD_EXTENSIONS'] = ['jpg', 'png', 'jpeg']
markers = [] 

def respond(message):
  response = MessagingResponse()
  response.message(message)
  return str(response)

def send_verification(sender_phone_number):
  phone = sender_phone_number
  client.verify \
    .services(VERIFY_SERVICE_SID) \
    .verifications \
    .create(to=phone, channel='sms')
    
def check_verification_token(phone, token):
  check = client.verify \
    .services(VERIFY_SERVICE_SID) \
    .verification_checks \
    .create(to=phone, code=token)    
  return check.status == 'approved'

def allowed_file(filename):
  return '.' in filename and filename.rsplit('.', 1)[1].lower() in app.config['UPLOAD_EXTENSIONS']
  # returns T/F if '.' in filename and the extension is parsed correctly 

# #############################################################
#
# map route
#
# #############################################################

@app.route('/map')
def mapview(): 
  try:
      conn = sqlite3.connect('app.db')
      print("Successful connection!")
      cur = conn.cursor()
      retrieve_img_url_query = """SELECT latitude, longitude, file_name FROM uploads;"""
      cur.execute(retrieve_img_url_query)      
      img_urls = cur.fetchall()
      for entry in img_urls: 
        print("[DATA] : parsed img url = ", entry)
        markers.append({
          'icon': 'http://maps.google.com/mapfiles/ms/icons/green-dot.png',
          'lat': entry[0], 
          'lng': entry[1],
          'infobox': '<div id="bodyContent">' +
              '<img src="' + entry[2] + '" alt = "sky" style="width:175px;height:220px;"></img>' + '</div>' 
        })
      print("[DATA] : markers = ", markers)

  except sqlite3.Error as e:
    print(e)
  finally:
    if conn:
      conn.close()
    else:
      print('Uh-oh')
  
  mymap = Map(
    identifier="sndmap",
    style=(
        "height:100%;"
        "width:100%;"
        "top:0;"
        "position:absolute;"
        "z-index:200;"
        "zoom: -9999999;"
    ),
    # these coordinates re-center the map
    lat=37.805355,
    lng=-122.322618,
    markers=markers,
  )
  return render_template('map.html', mymap=mymap)
  
# #############################################################
#
# whatsapp portion
#
# #############################################################

@app.route('/webhook', methods=['POST'])
def reply():
  sender_phone_number = request.form.get('From')
  media_msg = request.form.get('NumMedia')    # 1 if its a picture 
  latitude = request.values.get('Latitude')
  longitude = request.values.get('Longitude')

  try:
    conn = sqlite3.connect('app.db')
    print("Successful connection!")
    cur = conn.cursor()
    query = """SELECT EXISTS (SELECT 1 FROM uploads WHERE phone_number = (?))"""
    cur.execute(query, [sender_phone_number])      
    query_result = cur.fetchone()
    user_exists = query_result[0]

    # if user is not in the database and sends a word message such as "hello"
    if user_exists == 0 and media_msg == '0' and latitude is None and longitude is None:
      return respond('Please submit coordinates through the WhatsApp mobile app.')
      # print('Please submit coordinates through the WhatsApp mobile app.')

    # if the user is already in the database but sends a word message such as "hello"
    elif user_exists == 1 and media_msg == '0':
      return respond('Please send in a picture')

    # if the user doesn't exist in the database yet and sends in their location data
    elif user_exists == 0 and latitude and longitude:
      insert_users = ''' INSERT INTO uploads(phone_number, latitude, longitude, file_name, file_blob)
        VALUES(?,?,?,?,?) '''
      cur = conn.cursor()
      cur.execute(insert_users, (sender_phone_number, latitude, longitude, "PIC URL HERE", "BLOB UNNECESSARY",))
      conn.commit()
      return respond('Thanks for sending in your location! Finish your entry by sending in a photo of the sky.')
    
    # if the user exists in the database and sends in a media message
    elif user_exists == 1 and media_msg == '1':
      pic_url = request.form.get('MediaUrl0')
      look_up_user_query = """SELECT id FROM uploads WHERE phone_number = (?)"""
      cur.execute(look_up_user_query, [sender_phone_number]) 
      query_result = cur.fetchone()
      user_id = query_result[0]
      pic_url = request.form.get('MediaUrl0')  

      relevant_tags = get_tags(pic_url)
      print("The tags for your picture are : ", relevant_tags)
      if 'sky' in relevant_tags:
        update_user_picture = '''UPDATE uploads
          SET file_name = ?
          WHERE id = ?'''
        cur = conn.cursor()
        cur.execute(update_user_picture, (pic_url, user_id))
        conn.commit()
        print("[INFO] : sender has set their pic ")
        return respond('You\'re all set!')
      else: 
        return respond('Please send in a picture of the sky.')
    else:
      return respond('Please send your current location, then send a picture of the sky.')
  except Error as e:
    print(e)
  finally:
    if conn:
      conn.close()
    else:
      error = "how tf did u get here."

# #############################################################
#
# code for non-whatsapp users here
#
# #############################################################

@app.route('/register', methods=['GET', 'POST'])
def register():
  if request.method == 'POST':
    print(request.form)
    sender_phone_number = request.form['formatted_number']
    latitude = request.form['latitude']
    longitude = request.form['longitude']
    print("[INFO] :", sender_phone_number, " sent in the coordinates - ", latitude, " ,", longitude)

    try:
      conn = sqlite3.connect('app.db')
      print("Successful connection!")
      cur = conn.cursor()
      query = """SELECT EXISTS (SELECT 1 FROM uploads WHERE phone_number = (?))"""
      cur.execute(query, [sender_phone_number])      
      query_result = cur.fetchone()
      user_exists = query_result[0]
      
      # if phone number not in db, add to db then send them to verify their acc
      if user_exists == 0: 
        session['sender_phone_number'] = sender_phone_number
        insert_users = ''' INSERT INTO uploads(phone_number, latitude, longitude, file_name, file_blob)
          VALUES(?,?,?,?,?) '''
        cur = conn.cursor()
        cur.execute(insert_users, (sender_phone_number, latitude, longitude, "PIC NAME HERE", "BLOB TBD",))
        conn.commit()
        print("[DATA] : successfully inserted into db")
        send_verification(session['sender_phone_number'])
        print("[INFO] : user needs to get their verification code now")
        return redirect(url_for('generate_verification_code'))

    # if phone number in db, send verification code
      if user_exists == 1: 
        session['sender_phone_number'] = sender_phone_number
        send_verification(sender_phone_number)
        print("[INFO] : user already exists so sending verification code now")
        return redirect(url_for('generate_verification_code'))
      return ("unsure lol????")
    except Error as e:
      print(e)
    finally:
      if conn:
        conn.close()
      else:
        error = "how tf did u get here."
  return render_template('register.html')
      
@app.route('/verifyme', methods=['GET', 'POST'])
def generate_verification_code():
  sender_phone_number = session['sender_phone_number']
  error = None
  if request.method == 'POST':
    verification_code = request.form['verificationcode']
    if check_verification_token(sender_phone_number, verification_code):
      return redirect(url_for('upload_file'))
    else:
      error = "Invalid verification code. Please try again."
      return render_template('verifypage.html', error = error)
  return render_template('verifypage.html')

@app.route('/upload')
def upload_file():
  return render_template('uploadpage.html')

@app.route('/uploader', methods = ['GET', 'POST'])
def submitted_file():
  sender_phone_number = session['sender_phone_number']
  if request.method == 'POST':
    f = request.files['file']
    if f and allowed_file(f.filename):
      user_secure_filename = secure_filename(f.filename)
      f.save(os.path.join(UPLOAD_FOLDER, user_secure_filename))
      s3_key = f"uploads/{user_secure_filename}"
      s3upload_file(s3_key, BUCKET)
      presigned_url = get_presigned_url(BUCKET, s3_key)
      
      # the file will be inserted into S3 and the key to retrieve it (uploads/{user_secure_filename}) will be in SQLite3 db
      relevant_tags = get_tags(presigned_url)
      print("The tags for your picture are : ", relevant_tags)
      if 'sky' in relevant_tags:
        try:
          conn = sqlite3.connect('app.db')
          print("Successful connection!")
          cur = conn.cursor()
          look_up_user_query = """SELECT id FROM uploads WHERE phone_number = (?)"""
          cur.execute(look_up_user_query, [sender_phone_number]) 
          query_result = cur.fetchone()
          user_id = query_result[0]
          update_user_picture = '''UPDATE uploads
            SET file_name = ?,
              file_blob = ?
            WHERE id = ?'''
          cur = conn.cursor()
          cur.execute(update_user_picture, (s3_key, presigned_url, user_id))
          conn.commit()
          print("[INFO] : sender has set their pic ")
          return render_template('success.html')
        except Error as e:
          print(e)
        finally:
          if conn:
            conn.close()
          else:
            error = "how tf did u get here."
      else: 
        error = "Please upload a picture of the sky."
        return render_template('uploadpage.html', error = error)
    else:
      error = "Please upload a valid file in .jpg, .jpeg, or .png format."
      return render_template('uploadpage.html', error = error)
    
if __name__ == "__main__":
  main()
  