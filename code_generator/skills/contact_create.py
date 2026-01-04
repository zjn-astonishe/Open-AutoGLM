def contact_create(first_name, last_name, phone_number):
    """
    Creates a new contact in the Contacts app with the provided details.
    
    This function abstracts the workflow for creating a new contact by launching
    the Contacts app, entering the contact details (first name, last name, and phone number),
    and saving the contact.
    
    Args:
        first_name (str): The first name of the contact to be created
        last_name (str): The last name of the contact to be created
        phone_number (str): The phone number of the contact to be created
    
    Returns:
        list: A list of action dictionaries representing the steps to create a contact
    """
    actions = []
    
    # Launch the Contacts app to begin creating a new contact
    actions.append({
        "action": "Launch",
        "app": "com.google.android.contacts"
    })
    
    # Tap the "+" button to start creating a new contact
    actions.append({
        "action": "Tap",
        "element": "com.google.android.contacts:id/floating_action_button|Create contact"
    })
    
    # Tap on the "First name" field to begin entering the contact's first name
    actions.append({
        "action": "Tap",
        "element": "com.google.android.contacts:id/editors|First name"
    })
    
    # Type the provided first name into the First name field
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
    
    # Type the provided last name into the Last name field
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
    
    # Type the provided phone number into the Phone field
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