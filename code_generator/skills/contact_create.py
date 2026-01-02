def contact_create(first_name, last_name, phone_number, app_package="com.google.android.contacts"):
    """
    Creates a new contact in the contacts app with the specified details.
    
    This function abstracts the workflow for creating a new contact by:
    - Opening the contacts application
    - Initiating the creation of a new contact
    - Filling in the contact details (first name, last name, phone number)
    - Saving the new contact
    
    Args:
        first_name (str): The first name of the contact to be created
        last_name (str): The last name of the contact to be created
        phone_number (str): The phone number of the contact to be created
        app_package (str): The package name of the contacts app (default: com.google.android.contacts)
    
    Returns:
        list: A list of action dictionaries representing the steps to create a contact
    """
    actions = []
    
    # Open the Contacts app
    actions.append({
        "action": "Tap",
        "element": "com.google.android.apps.nexuslauncher:id/icon|Contacts|Contacts"
    })
    
    # Tap the "+" button to create a new contact
    actions.append({
        "action": "Tap",
        "element": "com.google.android.contacts:id/floating_action_button|Create contact"
    })
    
    # Tap on the First name field to begin entering the contact's first name
    actions.append({
        "action": "Tap",
        "element": "com.google.android.contacts:id/editors|First name"
    })
    
    # Enter the first name in the First name field
    actions.append({
        "action": "Type",
        "element": "com.google.android.contacts:id/editors|First name",
        "text": first_name
    })
    
    # Tap on the Last name field to enter the last name
    actions.append({
        "action": "Tap",
        "element": "com.google.android.contacts:id/editors|Last name"
    })
    
    # Enter the last name in the Last name field
    actions.append({
        "action": "Type",
        "element": "com.google.android.contacts:id/editors|Last name",
        "text": last_name
    })
    
    # Tap on the Phone field to enter the phone number
    actions.append({
        "action": "Tap",
        "element": "com.google.android.contacts:id/editors|Phone"
    })
    
    # Enter the phone number in the Phone field
    actions.append({
        "action": "Type",
        "element": "com.google.android.contacts:id/editors|Phone",
        "text": phone_number
    })
    
    # Tap the "Save" button to save the new contact
    actions.append({
        "action": "Tap",
        "element": "com.google.android.contacts:id/toolbar_button|Save"
    })
    
    return actions