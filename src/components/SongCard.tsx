import React from 'react';
import { Play, Heart, ExternalLink, Music, Clock, Calendar } from 'lucide-react';
import { Button } from './ui/button';
import { Badge } from './ui/badge';

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

interface SongCardProps {
  song: Song;
  rank: number;
  searchType: 'melody' | 'lyrics' | 'both';
}

export function SongCard({ song, rank, searchType }: SongCardProps) {
  const getSimilarityColor = (similarity: number): string => {
    if (similarity >= 0.9) return 'text-green-600 bg-green-50';
    if (similarity >= 0.8) return 'text-blue-600 bg-blue-50';
    if (similarity >= 0.7) return 'text-yellow-600 bg-yellow-50';
    return 'text-gray-600 bg-gray-50';
  };

  const getSimilarityLabel = (similarity: number): string => {
    if (similarity >= 0.9) return 'Excellent Match';
    if (similarity >= 0.8) return 'Great Match';
    if (similarity >= 0.7) return 'Good Match';
    return 'Fair Match';
  };

  return (
    <div className="border border-gray-200 rounded-lg p-6 hover:shadow-md transition-shadow bg-white">
      <div className="flex items-start justify-between mb-4">
        <div className="flex items-start gap-4 flex-1">
          {/* Rank Badge */}
          <div className="flex-shrink-0">
            <div className="w-8 h-8 rounded-full bg-gradient-to-r from-purple-600 to-indigo-600 flex items-center justify-center text-white font-bold text-sm">
              {rank}
            </div>
          </div>

          {/* Album Art Placeholder */}
          <div className="w-16 h-16 bg-gradient-to-br from-purple-200 to-indigo-200 rounded-lg flex items-center justify-center flex-shrink-0">
            <Music className="w-8 h-8 text-purple-600" />
          </div>

          {/* Song Info */}
          <div className="flex-1 min-w-0">
            <h3 className="font-semibold text-lg text-gray-900 truncate">
              {song.title}
            </h3>
            <p className="text-gray-600 truncate">
              by {song.artist}
            </p>
            <p className="text-sm text-gray-500 truncate">
              {song.album} • {song.year}
            </p>
            
            {/* Song Details */}
            <div className="flex items-center gap-4 mt-2 text-sm text-gray-500">
              <div className="flex items-center gap-1">
                <Clock className="w-4 h-4" />
                {song.duration}
              </div>
              <div className="flex items-center gap-1">
                <Calendar className="w-4 h-4" />
                {song.year}
              </div>
            </div>
          </div>
        </div>

        {/* Similarity Score */}
        <div className="text-right flex-shrink-0">
          <div className={`inline-block px-3 py-1 rounded-full text-sm font-medium ${getSimilarityColor(song.similarity)}`}>
            {Math.round(song.similarity * 100)}% match
          </div>
          <p className="text-xs text-gray-500 mt-1">
            {getSimilarityLabel(song.similarity)}
          </p>
        </div>
      </div>

      {/* Genre Badge */}
      <div className="mb-3">
        <Badge variant="secondary" className="text-xs">
          {song.genre}
        </Badge>
      </div>

      {/* Match Reason */}
      <div className="mb-4 p-3 bg-gray-50 rounded-lg">
        <p className="text-sm text-gray-700">
          <span className="font-medium">Why it matches:</span> {song.matchReason}
        </p>
      </div>

      {/* Action Buttons */}
      <div className="flex items-center gap-2">
        <Button size="sm" className="flex items-center gap-2">
          <Play className="w-4 h-4" />
          Play Preview
        </Button>
        <Button size="sm" variant="outline">
          <Heart className="w-4 h-4" />
        </Button>
        <Button size="sm" variant="outline">
          <ExternalLink className="w-4 h-4" />
        </Button>
      </div>

      {/* Search Type Indicator */}
      <div className="mt-3 text-xs text-gray-500">
        Matched by: {
          searchType === 'melody' ? 'Musical patterns and melody' :
          searchType === 'lyrics' ? 'Lyrical themes and content' :
          'Both melody and lyrics'
        }
      </div>
    </div>
  );
}