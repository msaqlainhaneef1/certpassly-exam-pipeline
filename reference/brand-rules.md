# Brand rules

Re-read the latest owner rules before every stage. Mid-run changes have happened before.

## Site brand

CertPassly is the site brand. Pull the name and the independence disclaimer from `config/pipeline.yaml` (see `pipeline.example.yaml`). Never read them from application PHP.

The disclaimer begins: "CertPassly is an independent exam preparation platform..." Keep the full text from the config file on every page.

## Official vendor brands

Official vendor brands, product names, certification titles and exam codes are required on the pages that cover them. Use the vendor name from `config/vendors.yaml`, not a shortened or invented form.

## Banned in every page, import file, shared block and question

- Seller or competitor brands (the denylist in `pipeline.yaml` is the live list)
- Social or messaging links and names (Facebook, WhatsApp, Telegram, and similar)
- Phone numbers and email addresses
- "Free update" or "lifetime update" offers
- Typographic dashes (em dash or en dash). Use a comma, a colon, a hyphen, or "to".

`validate.py` and the extractor enforce these with the denylist and contact patterns. If you add a new banned term, put it in the config, not in a script.

## Contact

This site does not publish a phone number or a personal email on exam pages. Support contact belongs in the site's own contact page, not in imported content.
