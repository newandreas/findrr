# Internationalization (i18n) Setup Guide

This project uses Flask-Babel for multilingual support. To set up and manage translations, follow these steps.

## Initial Setup

### 1. Extract Translatable Strings

Run this command from the project root to extract all translation strings:

```bash
pybabel extract -F babel.cfg -o messages.pot .
```

This creates `messages.pot` file containing all translatable strings.

### 2. Initialize Language Catalogs

For each supported language, initialize a translation catalog:

```bash
pybabel init -i messages.pot -d translations -l es
pybabel init -i messages.pot -d translations -l fr
pybabel init -i messages.pot -d translations -l de
pybabel init -i messages.pot -d translations -l it
pybabel init -i messages.pot -d translations -l pt
pybabel init -i messages.pot -d translations -l ru
pybabel init -i messages.pot -d translations -l ja
pybabel init -i messages.pot -d translations -l zh
pybabel init -i messages.pot -d translations -l ko
pybabel init -i messages.pot -d translations -l ar
```

This creates `.po` files in `translations/<lang>/LC_MESSAGES/messages.po`.

## Translation Workflow

### 3. Translate Strings

Edit the `.po` files in `translations/<lang>/LC_MESSAGES/messages.po` with your translations:

```
#: app.py:XX
msgid "Status"
msgstr "Estado"  # Spanish example
```

### 4. Compile Translations

After translating, compile the translations to `.mo` files:

```bash
pybabel compile -d translations
```

This creates `.mo` files that Flask-Babel uses at runtime.

### 5. Update Existing Translations

If you add new strings, update all language catalogs:

```bash
pybabel extract -F babel.cfg -o messages.pot .
pybabel update -i messages.pot -d translations
```

Then re-edit the `.po` files and recompile.

## Directory Structure

After setup, your project will have:

```
findrr-of-bad-files/
├── translations/
│   ├── es/
│   │   └── LC_MESSAGES/
│   │       ├── messages.po
│   │       └── messages.mo
│   ├── fr/
│   │   └── LC_MESSAGES/
│   │       ├── messages.po
│   │       └── messages.mo
│   └── ... (other languages)
├── babel.cfg
├── messages.pot
└── app.py
```

## Supported Languages

- **en** - English (default)
- **es** - Spanish
- **fr** - French
- **de** - German
- **it** - Italian
- **pt** - Portuguese
- **ru** - Russian
- **ja** - Japanese
- **zh** - Chinese
- **ko** - Korean
- **ar** - Arabic
- **no** - Norwegian

## Features Implemented

✅ **Setting Storage**: User's language preference is saved to `settings.json`  
✅ **Browser Auto-Detection**: Falls back to browser locale if no preference is set  
✅ **Language Switcher**: Dropdown language selector on all pages  
✅ **Template Translations**: All UI strings marked with `{{ _('text') }}`  
✅ **JavaScript Translations**: Dynamic UI updates with i18n object  
✅ **Python Backend Translations**: API messages use gettext  

## Quick Commands

```bash
# Extract strings from code
pybabel extract -F babel.cfg -o messages.pot .

# Initialize new language (replace 'de' with language code)
pybabel init -i messages.pot -d translations -l de

# Update all language files with new strings
pybabel update -i messages.pot -d translations

# Compile translations for use
pybabel compile -d translations

# Combine all operations
pybabel extract -F babel.cfg -o messages.pot . && pybabel update -i messages.pot -d translations && pybabel compile -d translations
```

## Docker Deployment

When building the Docker image, translations will be compiled automatically if you add this to your `Dockerfile` build steps:

```dockerfile
RUN pybabel compile -d translations
```

## Adding New Strings

1. Add `{{ _('Your new string') }}` to templates
2. Or use `gettext('Your new string')` in Python code
3. Run `pybabel extract -F babel.cfg -o messages.pot .`
4. Run `pybabel update -i messages.pot -d translations`
5. Edit the `.po` files to add translations
6. Run `pybabel compile -d translations`

## Testing Translations

Change your browser's language preference to test translations without saving them to settings.

The locale selector will use:
1. Saved user preference (from settings)
2. Browser language (if no preference saved)
3. English (fallback)
