from app.nodes.user_profile.load_profile_node import ProfileLoaderNode


state = {
    "travellerId": "749d1059-cbcc-47bd-ab96-5f8f1ecb70cd",
    "user_id": "df55d964-039d-4838-8e5e-352ce1708bd9",
}

node = ProfileLoaderNode()

result = node.run(state)

print(result)