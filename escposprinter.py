import imaplib
import email
from io import BytesIO
from PIL import Image
import escpos.printer
from datetime import datetime
import time

# email account credentials
imap = imaplib.IMAP4_SSL("imap.gmail.com")
username = 'username@gmail.com'
password = 'password'

# printer
p = escpos.printer.Usb(0x04b8, 0x0e20, profile='TM-P80')
p.set(align='center')

# date and caption
now = datetime.now()
dt_string = now.strftime("\n%d/%m/%y %H:%M")
caption = (dt_string + "\n@ Your text here !")

# run an infinite loop to check for new messages every 15 seconds
count = 0
while True:
    try:
        # add count
        count += 1

        # create an IMAP client object and login
        logger.info("Cycle (count=%d) Connecting", count)
        imap.login(username, password)

        # select the inbox folder
        logger.info("Selecting inbox")
        imap.select("inbox")

        # search for new messages
        logger.info("Searching")
        result, data = imap.uid('search', None, '(ALL)')
        uids = data[0].split()
        if not uids:
            logger.info("No new messages found")

        # iterate through each new message               
        for uid in uids:
            # skip messages that have already been processed
            if uid in processed_uids:
                logger.info("skipping message")
                continue

            # fetch the message by UID
            logger.info("Processing message %s..." % uid)
            result, msg = imap.uid("fetch", uid, "(RFC822)")

            # parse the message into an email object
            email_message = email.message_from_bytes(msg[0][1])

            # iterate through each attachment
            for part in email_message.walk():
                if part.get_content_maintype() == 'multipart':
                    continue
                if part.get('Content-Disposition') is None:
                    continue

                # check if the attachment is a jpg or png file
                filename = part.get_filename()
                if filename and (filename.endswith(".jpg") or filename.endswith(".png")):
                    try:
                        # read the image data from the attachment
                        logger.info("Processing attachment %s..." % filename)
                        image_data = BytesIO(part.get_payload(decode=True))
                    except Exception as e:
                        logger.error("couldnt process attachment %s" % filename)
                        p.text("Error converting image")
                        p.cut()

                    # create a Pillow Image object
                    img = Image.open(image_data)
                    
                    # normalize the image orientation
                    try:
                        for orientation in ExifTags.TAGS.keys():
                            if ExifTags.TAGS[orientation] == 'Orientation':
                                break
                        exif = dict(img._getexif().items())

                        if exif[orientation] == 3:
                            img = img.rotate(180, expand=True)
                        elif exif[orientation] == 6:
                            img = img.rotate(270, expand=True)
                        elif exif[orientation] == 8:
                            img = img.rotate(90, expand=True)
                    except (AttributeError, KeyError, IndexError):
                        # cases where there is no exif data available
                        pass
                    
                    # resize the image to fit the printer width
                    max_width = 576 # maximum width of the TM M30 printer
                    w, h = img.size
                    if w > max_width:
                        ratio = max_width / float(w)
                        h = int((float(h) * float(ratio)))
                        img = img.resize((max_width, h), Image.ANTIALIAS)
                        # convert the image to grayscale
                        img = img.convert('L')

                        # apply Bayer matrix dithering
                        dither_matrix = np.array([[0, 48, 12, 60, 3, 51, 15, 63],
                                                [32, 16, 44, 28, 35, 19, 47, 31],
                                                [8, 56, 4, 52, 11, 59, 7, 55],
                                                [40, 24, 36, 20, 43, 27, 39, 23],
                                                [2, 50, 14, 62, 1, 49, 13, 61],
                                                [34, 18, 46, 30, 33, 17, 45, 29],
                                                [10, 58, 6, 54, 9, 57, 5, 53],
                                                [42, 26, 38, 22, 41, 25, 37, 21]])
                        dither_matrix = (dither_matrix / 64) * 255
                        dither_matrix = np.tile(dither_matrix, (int(new_h/8)+1, int(new_w/8)+1))[:new_h, :new_w]

                        img = np.array(img)
                        img_dithered = np.zeros_like(img)
                        img_dithered[img > dither_matrix] = 255

                        # convert numpy array back to Pillow Image object
                        img_dithered = Image.fromarray(img_dithered.astype(np.uint8))

                        # print the image on the thermal printer
                        p.image(img_dithered)
                        logger.info("Printing %s" % filename)                       
                    
                        # add caption and cut
                        p.text(caption)
                        p.cut()

                        # mark the email for deletion
                        imap.uid("STORE", uid, "+FLAGS", "(\Deleted)")
                        
        # permanently delete the marked emails and expunge the mailbox
        imap.expunge()
        
        # close the connection to the email server
        logger.info("Logging out of IMAP server...")
        imap.close()
        imap.logout()

        # wait for 15 seconds before checking for new messages again
        time.sleep(15)

    except KeyboardInterrupt:
        break    
