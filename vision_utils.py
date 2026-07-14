"""
Scaffolding for Computer Vision (OpenCV) integration.
These functions serve as templates for finding images on the screen using template matching.
"""

# import cv2
# import numpy as np

def find_image_on_screen(template_path: str, screen_image_path: str, threshold: float = 0.8) -> tuple[int, int] | None:
    """
    Finds a template image within a larger screen image.

    Args:
        template_path: Path to the image you want to find (e.g., 'login_button.png').
        screen_image_path: Path to the current screenshot of the virtual phone screen.
        threshold: Confidence threshold for a match (0.0 to 1.0).

    Returns:
        A tuple (x, y) representing the center coordinates of the found image, or None if not found.
    """
    # TODO: Implement actual OpenCV logic here once game assets are available.
    # Example OpenCV implementation:
    #
    # img_screen = cv2.imread(screen_image_path, 0)
    # img_template = cv2.imread(template_path, 0)
    # w, h = img_template.shape[::-1]
    #
    # res = cv2.matchTemplate(img_screen, img_template, cv2.TM_CCOEFF_NORMED)
    # loc = np.where(res >= threshold)
    #
    # if len(loc[0]) > 0:
    #     # Return center of the first match
    #     pt = (loc[1][0], loc[0][0])
    #     center_x = pt[0] + w // 2
    #     center_y = pt[1] + h // 2
    #     return (center_x, center_y)

    return None

def is_image_present(template_path: str, screen_image_path: str, threshold: float = 0.8) -> bool:
    """
    Checks if a template image is present on the screen.
    """
    return find_image_on_screen(template_path, screen_image_path, threshold) is not None
