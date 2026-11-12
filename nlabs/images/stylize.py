# images/stylize.py — optional painterly filter for GENERIC photos (config stylize_generic_photos).
# Never applied to photos of the subject or any real person.
# Marks the credit as "modified".
def stylize(bgr):
    import cv2
    return cv2.stylization(bgr, sigma_s=40, sigma_r=0.35)
