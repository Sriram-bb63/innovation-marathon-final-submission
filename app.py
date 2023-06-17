import os
import re
import smtplib
from datetime import datetime
from email.mime.image import MIMEImage
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import cv2
import pandas as pd
import pymongo as mongo
import pytesseract
from dateparser import parse
from flask import Flask, make_response, redirect, render_template, request, send_file, url_for
from pytesseract import Output
from werkzeug.utils import secure_filename

app = Flask(__name__)

from_gmail = os.environ.get("FROM_GMAIL")
from_gmail_key = os.environ.get("FROM_GMAIL_KEY")
url = f"mongodb://localhost:27017"
client = mongo.MongoClient(url)
db = client["404-found"]

pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'

poster_directory = "sample"

def ocr_from_image(imgsrc):
    try:
        img = cv2.imread(imgsrc)
        d = pytesseract.image_to_data(img, output_type=Output.DICT)
        lis = d['text']
        string = " ".join(lis)
        regexes = [
            r"((19|20)?\d{1,2}\s?[-/]\s?\d{1,2}\s?[-/]\s?(19|20)?\d{2})|"\
            r"((Jan|Feb|Mar|Apr|May|Jun|June|Jul|Aug|Sept|Sep|Oct|Nov|Dec)"\
            r"\s?\d{1,2}\s?[,']?\s?(19|20)?\d{2})|(\d{1,2}\s?[-/]?\s?"\
            r"(Jan|Feb|Mar|Apr|May|Jun|June|Jul|Aug|Sept|Sep|Oct|Nov|Dec)"\
            r"\s?[',-/]?\s?(19|20)?\d{1,2})",

            r"\b(0?[1-9]|[12]\d|3[01]) (Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s\d{4}\b", # dd Mon yyyy
            r"\b(0?[1-9]|[12]\d|3[01]) (jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\s\d{4}\b", # dd mon yyyy

            r"\b(0?[1-9]|[12]\d|3[01]) (Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s\d{2}\b", # dd Mon yy
            r"\b(0?[1-9]|[12]\d|3[01]) (jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\s\d{2}\b", # dd mon yy

            r"\b(0?[1-9]|[12]\d|3[01]) (January|February|March|April|May|June|July|Augest|September|October|November|December),\d{2}\b", # dd Month,yy
            r"\b(0?[1-9]|[12]\d|3[01]) (january|february|march|april|may|june|july|augest|september|october|november|december),\d{2}\b", # dd month,yy

            r"\b(0?[1-9]|[12]\d|3[01]) (January|February|March|April|May|June|July|Augest|September|October|November|December),\d{4}\b", # dd Month,yyyy
            r"\b(0?[1-9]|[12]\d|3[01]) (january|february|march|april|may|june|july|augest|september|october|november|december),\d{4}\b", # dd month,yyyy
            
            r"\b(January|February|March|April|May|June|July|Augest|September|October|November|December)\s(0?[1-9]|[12]\d|3[01]),\s\d{4}\b", # Month dd, yyyy
            r"\b(january|february|march|april|may|june|july|augest|september|october|november|december)\s(0?[1-9]|[12]\d|3[01]),\s\d{4}\b", # month dd, yyyy
        ]
        matches = []
        for regex in regexes:
            match = re.findall(regex, string)
            matches.append(match)
        if len(matches) == 0:
            return False, None
        return True, parse(matches[0][0][0])
    except IndexError:
        return False, None

def mail_otp(name, to_gmail, event):
    message = MIMEMultipart()
    html = f"""
    <html>
        <head></head>
            <body>
                <p>Hello {name},</p>
                <p>This is a confirmation mail for you registration in the below event</p>
                <p>Event name: {event['name']}</p>
                <p>Event date: {event['date'].strftime("%d-%m-%Y")}</p>
                <p>Event venue: {event['venue']}</p>
                <br>
                <img src="cid:image1">
            </body>
    </html>
    """
    body = MIMEText(html, 'html')
    message.attach(body)
    with open(f"./static/images/{event['poster']}", "rb") as f:
        img_data = f.read()
        image = MIMEImage(img_data, name="test0.png")
        image.add_header('Content-ID', '<image1>')
        image.add_header('Content-Disposition', 'inline', filename='image.jpg')
        message.attach(image)
    message["Subject"] = f"Confirmation mail for {event['name']}"
    message["From"] = from_gmail
    message["To"] = to_gmail
    with smtplib.SMTP("smtp.gmail.com", 587) as server:
        server.starttls()
        server.login(from_gmail, from_gmail_key)
        server.sendmail(from_gmail, to_gmail, message.as_string())


@app.route("/", methods=["GET", "POST"])
@app.route("/login", methods=["GET", "POST"])
def index():
    message = ""
    if request.method == "POST":
        user_collection = db["users"]
        user_role = request.form.get("role")
        username = request.form.get("username")
        password = request.form.get("password")
        existing_user = user_collection.find_one(
            {
                "username": username 
            }
        )
        if existing_user:
            if existing_user["password"] == password:
                resp = make_response(redirect("/view-events"))
                resp.set_cookie("role", user_role)
                return resp
        message = "Login failed"
    return render_template("login.html", message=message)

@app.route("/about", methods=["GET"])
def about():
    return render_template("about.html")

@app.route("/contact", methods=["GET"])
def contact():
    return render_template("contact.html")

@app.route("/create-event", methods=["GET", "POST"])
def create_event():
    role = request.cookies.get("role")
    if role == "admin":
        if request.method == "POST":
            poster = request.files.get("poster")
            event_name = request.form.get("name")
            poster_file_path = os.path.join("static", "images", event_name + "." + poster.filename.split(".")[-1])
            poster.save(poster_file_path)
            event_venue = request.form.get("venue")
            registration_limit = int(request.form.get("limit"))
            organizer = request.form.get("organizer")
            events_collection = db["events"]
            ocr_status, event_date = ocr_from_image(poster_file_path)
            try:
                event_id = int(list(events_collection.find({}))[-1]["event_id"]) + 1
            except Exception as e:
                event_id = 1
            events_collection.insert_one(
                {
                    "event_id": event_id,
                    "poster": event_name + "." + poster.filename.split(".")[-1],
                    "name": event_name,
                    "date": event_date,
                    "venue": event_venue,
                    "organizer": organizer,
                    "event_status":"open",
                    "limit": registration_limit,
                    "registered": 0,
                    "registrations": []
                }
            )
            if ocr_status == False:
                return redirect(f"/edit-event?event_id={event_id}")
            message = {
                "color": "green-text",
                "title": "Success",
                "body": f"OCR detected date: {event_date.strftime('%d-%m-%Y')}",
                "edit_event": event_id
            }
            return render_template("information.html", message=message)
        venue_collection = db["venues"]
        venues = [venue["name"] for venue in venue_collection.find({})]
        return render_template("create_event.html", venues=venues)
    else:
        message = {
            "color": "red",
            "title": "Access denied",
            "body": "This role is not permitted to access this part of the site"
        }
        return render_template("information.html", message=message)

@app.route("/view-events", methods=["GET", "POST"])
def view_evevnt():
    role = request.cookies.get("role")
    # if request.method == "POST":
    from_date = request.args.get("from_date")
    to_date = request.args.get("to_date")
    if from_date:
        print("186")
        from_date = datetime.strptime(from_date, "%Y-%m-%d")
    if to_date:
        print("189")
        to_date = datetime.strptime(to_date, "%Y-%m-%d")
    venue = request.args.get("venue")
    organizer = request.args.get("organizer")
    # past_events = request.args.get("past_events")
    # full = request.args.get("full_events")
    filters = {}
    if from_date or to_date:
        filters = {
            "date": {}
        }
    if from_date:
        filters["date"]["$gt"] = from_date
    if to_date:
        filters["date"]["$lt"] = to_date
    if venue and venue != "all":
        filters["venue"] = venue
    if organizer and organizer != "all":
        filters["organizer"] = organizer
    print(filters)
    events_collection = db["events"]
    events_collection_list = [event for event in events_collection.find(filters)][::-1]
    venue_collection = db["venues"]
    venues = [venue["name"] for venue in venue_collection.find({})]
    # Below line returns only future events
    # events_collection_list = [event for event in events_collection.find({
    #     "date": {
    #         "$gt": datetime.now()
    #     }
    # })][::-1]
    return render_template("view_events.html", events=events_collection_list, venues=venues, role=role)

@app.route("/edit-event", methods=["GET", "POST"])
def edit_event():
    role = request.cookies.get("role")
    if role == "admin":
        event_id = int(request.args.get("event_id"))
        events_collection = db["events"]
        event = events_collection.find_one(
            {
                "event_id": event_id
            }
        )
        if event:
            if request.method == "POST":
                poster = request.files.get("poster")
                event_name = request.form.get("name")
                event_date = datetime.strptime(request.form.get("date"), "%Y-%m-%d")
                event_venue = request.form.get("venue")
                event_organizer = request.form.get("organizer")
                event_register_status = request.form.get("event_status")
                event_limit = int(request.form.get("limit"))
                if poster.filename != "":
                    poster_file_path = os.path.join(poster_directory, secure_filename(event_name + "." + poster.filename.split(".")[-1]))
                    poster.save(poster_file_path)
                    events_collection.update_one(
                        {
                            "event_id": event_id
                        },
                        {
                            "$set": {
                                "event_id": int(list(events_collection.find({}))[-1]["event_id"]) + 1,
                                "poster": event_name + "." + poster.filename.split(".")[-1],
                                "name": event_name,
                                "date": event_date,
                                "venue": event_venue,
                                "organizer": event_organizer,
                                "event_status": event_register_status,
                                "limit": event_limit
                            }
                        }
                    )
                else:
                    events_collection.update_one(
                        {
                            "event_id": event_id
                        },
                        {
                            "$set": {
                                "event_id": int(list(events_collection.find({}))[-1]["event_id"]) + 1,
                                "name": event_name,
                                "date": event_date,
                                "venue": event_venue,
                                "organizer": event_organizer,
                                "event_status":event_register_status,
                                "limit": event_limit
                            }
                        }
                    )
                message = {
                    "color": "green-text",
                    "title": "Success",
                    "body": "You have successfully edited the event"
                }
                return render_template("information.html", message=message)
            venue_collection = db["venues"]
            venues = [venue["name"] for venue in venue_collection.find({})]
            return render_template("edit_event.html", event=event, venues=venues)
        else:
            return redirect("/404-raise-error") # Non existant route to raise 404 error
   
    else:
        message = {
            "color": "red",
            "title": "Access  denied",
            "body": "This role is not permitted to access this part of site"
        }
        return render_template("information.html", message=message)

@app.route("/delete-event", methods=["GET", "POST"])
def delete_event():
    role = request.cookies.get("role")
    if role == "admin":
        event_id = int(request.args.get("event_id"))
        events_collection = db["events"]
        events_collection.delete_one(
            {
                "event_id": event_id
            }
        )
        return redirect("/view-events")
        # message = {
        #     "color": "green-text",
        #     "title": "Success",
        #     "body": "You have successfully deleted the event"
        # }
        # return render_template("information.html", message=message)
    else:
        message = {
            "color": "red",
            "title": "Access denied",
            "body": "This role is not permitted to access this part of the site"
        }
        return render_template("information.html", message=message)

@app.route("/register", methods=["GET", "POST"])
def register():
    role = request.cookies.get("role")
    event_id = int(request.args.get("event_id"))
    if role == "student":
        events_collection = db["events"]
        event = events_collection.find_one(
            {
                "event_id": event_id
            }
        )
        if event["registered"] < event["limit"] and event["event_status"]=="open":
            if request.method == "POST":
                regno = request.form.get("regno")
                name = request.form.get("name")
                email = request.form.get("email")
                dept = request.form.get("dept")
                year = request.form.get("year")
                section = request.form.get("section")
                phone = request.form.get("phone")
                new_registration = {
                    "regno": regno,
                    "name": name,
                    "email": email,
                    "dept": dept,
                    "year": year,
                    "section": section,
                    "phone": phone
                }
                registrations = event["registrations"]
                for registration in registrations:
                    if registration["regno"] == regno:
                        message = {
                            "color": "red",
                            "title": "Already registered",
                            "body": "This register number has already registered for the event"
                        }
                        return render_template("information.html", message=message)
                events_collection.update_one(
                    {
                        "event_id": event_id
                    },
                    {
                        "$set": {
                            "registered": event["registered"] + 1
                        },
                        "$push": {
                            "registrations": new_registration
                        }
                    }
                )
                mail_otp(name, email, event)
                message = {
                    "color": "green-text",
                    "title": "Success",
                    "body": "You have successfully registered to this event"
                }
                return render_template("information.html", message=message)
            return render_template("register.html", event_id=event_id)
        elif(event['event_status']!="open"):
            message = {
            "color": "red",
            "title": "Registrations have been paused/closed",
            "body": "Please try again later"
                    }
            return render_template("information.html", message=message)        
        else:
            message = {
                "color": "red",
                "title": "No more seats available",
                "body": "Looks like the event got filled out pretty fast :("
            }
            return render_template("information.html", message=message)
    else:
        message = {
            "color": "red",
            "title": "Access denied",
            "body": "This role is not permitted to access this part of the site"
        }
        return render_template("information.html", message=message)

@app.route("/export", methods=["GET"])
def export():
    role = request.cookies.get("role")
    if role == "admin":
        event_id = int(request.args.get("event_id"))
        events_collection = db["events"]
        event = events_collection.find_one(
            {
                "event_id": event_id
            }
        )
        if event:
            event_name = event["name"]
            registrations = event["registrations"]
            df = pd.DataFrame(registrations)
            df.to_excel(f"exports/{event_id}_{event_name}.xlsx", index=False)
            message = {
                "color": "green-text",
                "title": "Ready to download",
                "body": f"Download {event_name}.xlsx by clicking the button below",
                "file": f"{event_id}_{event_name}.xlsx",
                "event_id": event_id
            }
            return render_template("information.html", message=message)
        else:
            return redirect("/404-raise-error") # Non existant route to raise 404 error
    else:
        message = {
            "color": "red",
            "title": "Access denied",
            "body": "This role is not permitted to access this part of the site"
        }
        return render_template("information.html", message=message)

@app.route("/download", methods=["GET"])
def download():
    role = request.cookies.get("role")
    if role == "admin":
        event_id = int(request.args.get("event_id"))
        print(event_id)
        events_collection = db["events"]
        event = events_collection.find_one(
            {
                "event_id": event_id
            }
        )
        if event:
            event_name = event["name"]
            path = f"exports/{event_id}_{event_name}.xlsx"
            return send_file(path, as_attachment=True)
        else:
            return redirect("/404-raise-error")
    else:
        message = {
            "color": "red",
            "title": "Access denied",
            "body": "This role is not permitted to access this part of the site"
        }
        return render_template("information.html", message=message)

@app.route("/logout", methods=["GET"])
def logout():
    resp = make_response(redirect("/"))
    resp.set_cookie("role", "", expires=0)
    return resp

@app.errorhandler(404)
def page_not_found(e):
    message = {
        "color": "red",
        "title": "404",
        "body": "The page you are looking for does not exist"
    }
    return render_template("information.html", message=message)

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0")