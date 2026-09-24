assets/
  icon.ico                   Application / installer icon. Regenerate with
                             `python tools/make_icon.py` (drawn in code, no
                             third-party artwork).
  controller_reference.png   Photo used by the "Photo" controller picture
                             (Settings > Appearance). The default "Illustration"
                             picture is drawn in code and needs no image.
  controller_calibration.json
                             Normalised (0..1) position of every control on
                             controller_reference.png.

IMPORTANT - controller_reference.png licensing:
This is a stock photo (the filename pattern suggests a Pixabay download).
Before publishing the repository or an installer, confirm you have the right
to redistribute it by checking the original source page. If in doubt, delete
it: the app falls back to the built-in illustration, and users can still load
their own photo from Settings > Appearance > Load your own photo.
