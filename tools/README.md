# tools

## build_product.py

Builds a product's help centre (`products/<slug>/help.html`) from the app's
own help articles and screenshots, so the website always matches the app.

1. In the app, capture the screens (needs the Flutter SDK, no device):

   ```
   cd ../dial-book/dialbook
   SHOTS=build/help_shots/phone SIZE=440x956  flutter test --dart-define=DIALBOOK_ANDROID_LOOK=true test_e2e/help_shots_test.dart
   SHOTS=build/help_shots/ipad  SIZE=1210x834 flutter test --dart-define=DIALBOOK_ANDROID_LOOK=true test_e2e/help_shots_test.dart
   ```

   (440×956 is an iPhone 17 Pro Max, 1210×834 an iPad Pro 11-inch on its
   side.) Each screen is saved as a PNG plus a JSON of every label on it
   with its position.

2. Build the page (needs Pillow: `pip3 install Pillow`):

   ```
   python3 tools/build_product.py products/dialbook \
     --app ../dial-book/dialbook \
     --phone ../dial-book/dialbook/build/help_shots/phone \
     --ipad  ../dial-book/dialbook/build/help_shots/ipad
   ```

   Screenshots are converted to WebP under `products/dialbook/img/`. Every
   `{label:key}` in an article becomes the real on-screen text, and labels
   that appear on the article's screenshot get a numbered marker.

Without `--phone`/`--ipad` the page is rebuilt from the images already in
`img/`.

## Adding a product

Copy `products/dialbook/` to `products/<slug>/`, edit `product.json`
(name, support email, store links, which screen each article shows), write
`index.html` and `privacy.html` for the product, and run the build. All
pages share `assets/site.css`.
