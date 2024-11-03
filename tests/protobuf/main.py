import person_pb2 # protoc --proto_path=. --python_out=. .\person.proto

# 메시지 생성
person = person_pb2.Person()
person.name = "Alice"
person.id = 123
person.email = "alice@example.com"

# 직렬화
serialized_person = person.SerializeToString()
print(type(serialized_person))

# 역직렬화
person_from_serialized = person_pb2.Person()
person_from_serialized.ParseFromString(serialized_person)

print(person_from_serialized)
