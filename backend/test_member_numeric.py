from app.services.trello.member_mapping import member_numeric_id
print("Type:", type(member_numeric_id(3298014399)))
print("Output:", member_numeric_id(3298014399))
print("Output str:", member_numeric_id(str(3298014399)))
