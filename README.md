# thermal-photoprinter
Personnal project to turn a thermal printer into a photoprinter using escpos and IMAPlib

Actually my very first coding project, so don't expect too much ahah

Step by step :
1. Login to IMAP server and check for new emails
2. Iterate through new message looking for .jpg or .png attachments
3. Load in Pillow, rotate and apply graphic effects
4. Print on thermal printer
5. Delete printed mails
6. Logout and restart

Still trying to figure out my options as graphic effects. Tried ordered dithering, thresholding, didn't manage to work around bayers dithering yet. Need to experiment some more.

Update : I've decided to use 8x8 bayer matrix to apply ordered dithering. I like the low tech render of the thermal printed pictures.

I will definitely keep updating this project. This is what I have in mind :
+ user generating personalized caption (emoji support)
+ better statistics
