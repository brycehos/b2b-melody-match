import React, { useState, useEffect } from 'react';
import { SongCard } from './SongCard';
import { Loader2, Music } from 'lucide-react';

interface Song {
  id: string;
  title: string;
  artist: string;
  album: string;
  year: number;
  similarity: number;
  matchReason: string;
  genre: string;
  duration: string;
}

interface SimilarSongsProps {
  searchQuery: string;
  searchType: 'melody' | 'lyrics' | 'both';
}

// Mock data outside component to avoid recreation
const MOCK_SONGS: Song[] = [
  {
    id: '1',
    title: 'Sweet Child O\' Mine',
    artist: 'Guns N\' Roses',
    album: 'Appetite for Destruction',
    year: 1987,
    similarity: 0.94,
    matchReason: 'Similar guitar riffs and rock ballad structure',
    genre: 'Hard Rock',
    duration: '5:03'
  },
  {
    id: '2',
    title: 'November Rain',
    artist: 'Guns N\' Roses',
    album: 'Use Your Illusion I',
    year: 1991,
    similarity: 0.89,
    matchReason: 'Epic rock ballad with piano and orchestral elements',
    genre: 'Rock Ballad',
    duration: '8:57'
  },
  {
    id: '3',
    title: 'Stairway to Heaven',
    artist: 'Led Zeppelin',
    album: 'Led Zeppelin IV',
    year: 1971,
    similarity: 0.87,
    matchReason: 'Progressive structure and emotional guitar solos',
    genre: 'Progressive Rock',
    duration: '8:02'
  },
  {
    id: '4',
    title: 'Free Bird',
    artist: 'Lynyrd Skynyrd',
    album: 'Pronounced Leh-nerd Skin-nerd',
    year: 1973,
    similarity: 0.85,
    matchReason: 'Extended guitar solos and southern rock style',
    genre: 'Southern Rock',
    duration: '9:07'
  },
  {
    id: '5',
    title: 'Hotel California',
    artist: 'Eagles',
    album: 'Hotel California',
    year: 1976,
    similarity: 0.83,
    matchReason: 'Intricate guitar work and storytelling lyrics',
    genre: 'Rock',
    duration: '6:30'
  },
  {
    id: '6',
    title: 'Comfortably Numb',
    artist: 'Pink Floyd',
    album: 'The Wall',
    year: 1979,
    similarity: 0.81,
    matchReason: 'Atmospheric soundscape and emotional guitar solos',
    genre: 'Progressive Rock',
    duration: '6:23'
  }
];

export function SimilarSongs({ searchQuery, searchType }: SimilarSongsProps) {
  const [isLoading, setIsLoading] = useState(true);
  const [results, setResults] = useState<Song[]>([]);

  useEffect(() => {
    setIsLoading(true);
    
    const timer = setTimeout(() => {
      const mockResults = MOCK_SONGS.map(song => ({
        ...song,
        matchReason: searchType === 'melody' ? `Musical similarity: ${song.matchReason}` :
                    searchType === 'lyrics' ? `Lyrical themes: ${song.matchReason}` :
                    `Combined match: ${song.matchReason}`
      }));
      
      setResults(mockResults);
      setIsLoading(false);
    }, 1500);

    return () => clearTimeout(timer);
  }, [searchQuery, searchType]);

  if (isLoading) {
    return (
      <div className="bg-white rounded-2xl shadow-xl p-8">
        <div className="flex flex-col items-center justify-center py-12">
          <Loader2 className="w-8 h-8 text-purple-600 animate-spin mb-4" />
          <h3 className="text-xl font-semibold text-gray-800 mb-2">
            Analyzing "{searchQuery}"
          </h3>
          <p className="text-gray-600 text-center max-w-md">
            Our AI is searching through thousands of songs to find the best matches based on {
              searchType === 'melody' ? 'musical patterns' :
              searchType === 'lyrics' ? 'lyrical content' :
              'both melody and lyrics'
            }...
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="bg-white rounded-2xl shadow-xl p-8">
      <div className="flex items-center gap-3 mb-6">
        <Music className="w-6 h-6 text-purple-600" />
        <h2 className="text-2xl font-semibold text-gray-800">
          Similar to "{searchQuery}"
        </h2>
      </div>

      <div className="mb-4 p-4 bg-purple-50 rounded-lg">
        <p className="text-sm text-purple-800">
          <span className="font-medium">Search Type:</span> {
            searchType === 'melody' ? 'Melody matching - focusing on musical patterns and rhythm' :
            searchType === 'lyrics' ? 'Lyrics matching - focusing on themes and lyrical content' :
            'Combined matching - considering both melody and lyrics'
          }
        </p>
      </div>

      <div className="space-y-4">
        {results.map((song, index) => (
          <SongCard 
            {/* key={song.id} */}
            song={song}
            rank={index + 1}
            searchType={searchType}
          />
        ))}
      </div>

      <div className="mt-6 p-4 bg-gray-50 rounded-lg text-center">
        <p className="text-sm text-gray-600">
          Results are generated using mock data. In a real implementation, these would come from a vector database with actual song embeddings.
        </p>
      </div>
    </div>
  );
}