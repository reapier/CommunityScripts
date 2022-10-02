import sys
import json
import time
import requests
import log
import config


class StashInterface:

    def __init__(self, fragment):
        self._start = time.time()
        self._fragment = fragment
        self._fragment_server = self._fragment["server_connection"]
        self._plugin_dir = self._fragment_server["PluginDir"]
        self._hook_type = self._fragment["args"]["hookContext"]["type"]
        self._scene_id = self._fragment["args"]["hookContext"]["id"]
        self._path_rewrite = self._fragment["args"].get("pathRewrite")
        log.LogDebug(
            f"Starting nfoSceneParser plugin for scene {self._scene_id}")

    def get_scene_id(self):
        return self._scene_id

    def getScene(self, scene_id):
        query = """
        query FindScene($id: ID!, $checksum: String) {
            findScene(id: $id, checksum: $checksum) {
                ...SceneData
            }
        }
        fragment SceneData on Scene {
            id
            organized
            path
        }
        """
        variables = {
            "id": scene_id
        }
        result = self.__callGraphQL(query, variables)
        # Path rewriting used for testing only
        if (self._path_rewrite is not None):
            result["findScene"]["path"] = result["findScene"]["path"].replace(
                self._path_rewrite[0], self._path_rewrite[1])
        return result.get("findScene")

    def updateScene(self, scene_id, scene_data):
        query = """
        mutation sceneUpdate($input: SceneUpdateInput!) {
            sceneUpdate(input: $input) {
                id
            }
        }    
        """
        input_data = {
            "id": scene_id,
            "title": scene_data["title"],
            "details": scene_data["details"],
            "date": scene_data["date"],
            "rating": scene_data["rating"],
            "url": scene_data["url"],
            "studio_id": scene_data["studio_id"],
            "performer_ids": scene_data["performer_ids"],
            "tag_ids": scene_data["tag_ids"],
        }
        if scene_data["cover_image"] is not None:
            input_data.update({"cover_image": scene_data["cover_image"]})
        # Update to "organized" according to config
        if config.set_organized_nfo and scene_data["source"] == "nfo":
            has_mandatory_tags = True
            scene_keys = [item[0].replace(
                "_id", "") if item[1] else None for item in scene_data.items()]
            for mandatory_tag in config.set_organized_only_if:
                if mandatory_tag not in scene_keys:
                    has_mandatory_tags = False
                    break
            if has_mandatory_tags:
                input_data.update({"organized": True})
        # Update movie if exists
        if scene_data["movie_id"] is not None:
            input_data["movies"] = {
                "movie_id": scene_data["movie_id"],
                "scene_index": scene_data["scene_index"],
            }
        variables = {
            "input": input_data
        }
        result = self.__callGraphQL(query, variables)
        return result.get("sceneUpdate")

    def performerCreate(self, name):
        query = """
        mutation performerCreate($input: PerformerCreateInput!) {
            performerCreate(input: $input) {
                id
            }
        }
        """
        variables = {
            "input": {
                "name": name
            }
        }
        result = self.__callGraphQL(query, variables)
        return result.get("performerCreate")

    def studioCreate(self, name):
        query = """
        mutation studioCreate($input: StudioCreateInput!) {
            studioCreate(input: $input) {
                id
            }
        }
        """
        variables = {
            "input": {
                "name": name
            }
        }
        result = self.__callGraphQL(query, variables)
        return result.get("studioCreate")

    def tagCreate(self, name):
        query = """
        mutation tagCreate($input: TagCreateInput!) {
            tagCreate(input: $input) {
                id
            }
        }
        """
        variables = {
            "input": {
                "name": name
            }
        }
        result = self.__callGraphQL(query, variables)
        return result.get("tagCreate")

    def movieCreate(self, file_data, studio_id, folder_data):
        query = """
        mutation movieCreate($input: MovieCreateInput!) {
            movieCreate(input: $input) {
                id
            }
        }
        """
        # Use folder nfo data for some movie specific attributes (ignoring scene nfo specifics)
        date = folder_data["date"] or file_data["date"]
        variables = {
            "input": {
                "name": file_data["movie"],
                "studio_id": studio_id if "studio" not in config.blacklist else None,
                "date": date if "date" not in config.blacklist else None,
                "director": file_data["director"] if "director" not in config.blacklist else None,
                "synopsis": folder_data["details"] if "details" not in config.blacklist else None,
                "rating": folder_data["rating"] if "rating" not in config.blacklist else None,
                "url": folder_data["url"] if "url" not in config.blacklist else None,
                "front_image": folder_data["cover_image"] if "cover_image" not in config.blacklist else None,
                "back_image": folder_data["other_image"] if "cover_image" not in config.blacklist else None,
            }
        }
        result = self.__callGraphQL(query, variables)
        return result.get("movieCreate")

    def findPerformers(self, name):
        query = """
        query findPerformers($performer_filter: PerformerFilterType, $filter: FindFilterType) {
            findPerformers(performer_filter: $performer_filter, filter: $filter) {
                performers {
                    id
                    name
                    aliases
                }
            }
        }
        """
        variables = {
            "performer_filter": {
                "name": {
                    "value": name,
                    "modifier": "INCLUDES"
                },
                "OR": {
                    "aliases": {
                        "value": name,
                        "modifier": "INCLUDES"
                    }
                }
            },
            "filter": {
                "per_page": -1
            },
        }
        result = self.__callGraphQL(query, variables)
        return result.get("findPerformers")

    def findStudios(self, name):
        query = """
        query findStudios($studio_filter: StudioFilterType, $filter: FindFilterType) {
            findStudios(studio_filter: $studio_filter, filter: $filter) {
                studios {
                    id
                    name
                    aliases
                }
            }
        }
        """
        variables = {
            "studio_filter": {
                "name": {
                    "value": name,
                    "modifier": "INCLUDES"
                },
                "OR": {
                    "aliases": {
                        "value": name,
                        "modifier": "INCLUDES"
                    }
                }
            },
            "filter": {
                "per_page": -1
            },
        }
        result = self.__callGraphQL(query, variables)
        return result.get("findStudios")

    def findMovies(self, name):
        query = """
        query findMovies($movie_filter: MovieFilterType, $filter: FindFilterType) {
            findMovies(movie_filter: $movie_filter, filter: $filter) {
                movies {
                    id
                    name
                }
            }
        }
        """
        variables = {
            "studio_filter": {
                "name": {
                    "value": name,
                    "modifier": "INCLUDES"
                }
            },
            "filter": {
                "per_page": -1
            },
        }
        result = self.__callGraphQL(query, variables)
        return result.get("findMovies")

    def findTags(self, name):
        query = """
        query findTags($tag_filter: TagFilterType, $filter: FindFilterType) {
            findTags(tag_filter: $tag_filter, filter: $filter) {
                tags {
                    id
                    name
                }
            }
        }
        """
        variables = {
            "tag_filter": {
                "name": {
                    "value": name,
                    "modifier": "INCLUDES"
                }
            },
            "filter": {
                "per_page": -1
            },
        }
        result = self.__callGraphQL(query, variables)
        return result.get("findTags")

    def exit_plugin(self, msg=None, err=None):
        if msg is None and err is None:
            msg = "plugin ended"
        log.LogDebug(f"Execution time: {round(time.time() - self._start, 3)}s")
        output_json = {"output": msg, "error": err}
        print(json.dumps(output_json))
        sys.exit()

    def __callGraphQL(self, query, variables=None):
        # Session cookie for authentication (supports API key for CLI tests)
        graphql_port = str(self._fragment_server["Port"])
        graphql_scheme = self._fragment_server["Scheme"]
        graphql_cookies = "" if self._fragment_server.get("SessionCookie") is None else {
            "session": self._fragment_server["SessionCookie"]["Value"]}
        graphql_headers = {
            "Accept-Encoding": "gzip, deflate, br",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Connection": "keep-alive",
            "DNT": "1"
        }
        graphql_api_key = self._fragment_server.get("ApiKey")
        if graphql_api_key is not None:
            graphql_headers.update({"ApiKey": graphql_api_key})
        graphql_domain = self._fragment_server["Host"]
        if graphql_domain == "0.0.0.0":
            graphql_domain = "localhost"
        # Stash GraphQL endpoint
        graphql_url = f"{graphql_scheme}://{graphql_domain}:{graphql_port}/graphql"

        graphql_json = {"query": query}
        if variables is not None:
            graphql_json["variables"] = variables
        try:
            response = requests.post(
                graphql_url, json=graphql_json, headers=graphql_headers, cookies=graphql_cookies, timeout=20)
        except Exception as e:
            self.exit_plugin(err=f"[FATAL] Error with the graphql request {e}")
        if response.status_code == 200:
            result = response.json()
            if result.get("error"):
                for error in result["error"]["errors"]:
                    raise Exception(f"GraphQL error: {error}")
                return None
            if result.get("data"):
                return result.get("data")
        elif response.status_code == 401:
            self.exit_plugin(err="HTTP Error 401, Unauthorised.")
        else:
            raise ConnectionError(
                f"GraphQL query failed: {response.status_code} - {response.content}")